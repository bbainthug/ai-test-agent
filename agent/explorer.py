"""探索器（D-B2）：planner 生成用例前自动探索真实页面。

职责与红线：
- 站点地图：登录一次，读取控制台侧边栏与前台导航的链接（文本 → URL），
  缓存到 <cache-dir>/site_map.json。**自动发现**——不从 features.json 或
  任何按功能写的事实里取路由。
- 页面快照：用已登录状态（storage_state 复用，**不重复登录**——Halo 登录
  限流 3 次/分钟）打开页面，返回脱敏、截断的文本快照。
- 一层展开：允许点击"树里存在的按钮"后再拍快照（新建对话框这类表单）；
  提交类按钮（保存/提交/发布/删除/确定/创建…）一律拒绝（黑名单可测试）。
- 全程只读：不创建、不修改、不删除任何数据；独立 browser context，
  不装故障、不计探针（否则污染覆盖率口径）。
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from .config import Settings
from .snapshot import redact, text_snapshot

# 提交类按钮黑名单：点击这类按钮会创建/修改/删除数据，违反探索只读红线。
# 匹配按钮可访问名（子串，归一空白）；列表在测试里逐项断言。
SUBMIT_BUTTON_BLACKLIST = (
    "保存", "提交", "发布", "删除", "确定", "确认", "创建", "新增", "添加",
    "登录", "注销", "退出", "重置", "应用", "上传", "安装", "卸载", "启用",
    "禁用", "还原", "恢复", "清空", "移除", "更新", "修改", "同步", "克隆",
)

_LINK_LINE_RE = re.compile(r"^\s*-\s+link\s+\"(.+?)\"")
_URL_LINE_RE = re.compile(r"^\s*-\s*/url:\s*(\S+)")


class ExplorerError(RuntimeError):
    """探索失败（登录失败、页面打不开等）——调用方应降级为 baseline planner。"""


def is_submit_button(name: str) -> bool:
    """按钮名是否命中提交类黑名单（空白归一后子串匹配）。"""
    normalized = re.sub(r"\s+", "", name or "")
    return any(word in normalized for word in SUBMIT_BUTTON_BLACKLIST)


class Explorer:
    """可以被多个规划线程共用一个实例：每次方法调用各自开关 Playwright/浏览器/
    context（不把它们存在 self 上），跨线程共享的只有站点地图缓存与耗时累加器，
    两者都用锁保护（见 _site_map_lock / _cost_lock）。"""

    def __init__(self, settings: Settings, cache_dir: Path) -> None:
        self.settings = settings
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._storage_state = self.cache_dir / "storage_state.json"
        self._site_map_path = self.cache_dir / "site_map.json"
        self._site_map: dict | None = None
        self._site_map_lock = threading.Lock()  # 保证一次运行只探索一次站点地图
        self._cost_lock = threading.Lock()  # explore_seconds 累加跨线程非原子，需保护
        self.explore_seconds = 0.0  # 累计探索墙钟（不含 LLM），成本单列

    # ------------------------------------------------------------------
    # 登录：全局只登一次（storage_state 文件 + mkdir 原子锁）
    # ------------------------------------------------------------------

    def _login_and_save(self) -> None:
        """登录一次并保存 storage_state；已登录则直接返回。

        调用方必须在**进入自己的 `with sync_playwright()` 之前**调用本方法——
        本方法自己会开一个 `with sync_playwright()`，同一线程内嵌套第二个
        `with sync_playwright()` 会报错（Playwright 同步 API 不允许同线程内
        嵌套）。`_new_context()` 因此不再调用本方法，改由 site_map() /
        page_snapshot() / expanded_snapshot() 各自在开 `with` 前先调用一次。
        """
        if self._storage_state.exists():  # 快路径：多数调用不用碰锁文件
            return
        lock = self.cache_dir / ".login.lock"
        # 简单文件锁：拿到锁的线程负责登录；其他线程等文件出现。
        acquired = False
        while True:
            try:
                lock.mkdir()
                acquired = True
                break
            except FileExistsError:
                if self._storage_state.exists():
                    return  # 别的线程已经登录完成
                time.sleep(0.5)
        if not acquired:  # pragma: no cover - 逻辑上不可达
            return
        try:
            if self._storage_state.exists():
                return
            base = self.settings.halo_base_url
            with sync_playwright() as p:
                browser = _launch(p, self.settings.headless)
                context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
                _block_external(context, self.settings.blocked_hosts)
                page = context.new_page()
                page.goto(f"{base}/login", wait_until="domcontentloaded",
                          timeout=self.settings.goto_timeout_ms)
                page.get_by_label("用户名").fill(self.settings.halo_admin_user)
                page.get_by_label("密码").fill(self.settings.halo_admin_password)
                page.get_by_role("button", name="登录").click()
                try:
                    page.wait_for_url("**/uc/profile**", timeout=15_000)
                except Exception as exc:
                    raise ExplorerError(f"登录后未跳到 /uc/profile: {exc}") from exc
                context.storage_state(path=str(self._storage_state))
                context.close()
                browser.close()
        except ExplorerError:
            raise
        except Exception as exc:
            raise ExplorerError(f"登录失败: {exc}") from exc
        finally:
            lock.rmdir()

    def _new_context(self, playwright):
        """在调用方已打开的 `with sync_playwright()` 里建浏览器 + context。

        不在这里调用 `_login_and_save()`——那会在同一线程内嵌套第二个
        `with sync_playwright()`（"Sync API inside the asyncio loop" 的根因）。
        调用方必须先在自己的 `with` 之外完成登录。
        """
        if not self._storage_state.exists():
            raise ExplorerError("登录状态不可用（调用方未先登录）")
        browser = _launch(playwright, self.settings.headless)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="zh-CN",
            storage_state=str(self._storage_state),
        )
        _block_external(context, self.settings.blocked_hosts)
        return browser, context

    # ------------------------------------------------------------------
    # 站点地图
    # ------------------------------------------------------------------

    def site_map(self) -> dict:
        """返回 {"console": [{"text","url"}...], "site": [...]}；结果缓存。

        加锁保证一次运行（不管有多少规划线程共用这个 Explorer 实例）只真正
        探索一次：第一个拿到锁的线程探索并写缓存，其余线程等锁释放后直接读
        内存/磁盘缓存，不重复打开浏览器。
        """
        if self._site_map is not None:
            return self._site_map
        with self._site_map_lock:
            if self._site_map is not None:  # 双检：等锁期间可能已被别的线程填好
                return self._site_map
            if self._site_map_path.exists():
                try:
                    self._site_map = json.loads(self._site_map_path.read_text(encoding="utf-8"))
                    return self._site_map
                except ValueError:
                    pass  # 缓存损坏则重新生成
            self._login_and_save()  # 必须在进入下面的 with sync_playwright() 之前
            t0 = time.monotonic()
            base = self.settings.halo_base_url
            console: list[dict] = []
            site: list[dict] = []
            with sync_playwright() as p:
                browser, context = self._new_context(p)
                try:
                    page = context.new_page()
                    page.goto(f"{base}/console/", wait_until="domcontentloaded",
                              timeout=self.settings.goto_timeout_ms)
                    page.wait_for_timeout(1500)  # 等侧边栏渲染
                    console = _extract_links(page, base)
                    page.goto(f"{base}/", wait_until="domcontentloaded",
                              timeout=self.settings.goto_timeout_ms)
                    page.wait_for_timeout(1000)
                    site = _extract_links(page, base)
                except ExplorerError:
                    raise
                except Exception as exc:
                    raise ExplorerError(f"站点地图探索失败: {exc}") from exc
                finally:
                    context.close()
                    browser.close()
            self._site_map = {"console": console, "site": site}
            self._site_map_path.write_text(
                json.dumps(self._site_map, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            with self._cost_lock:
                self.explore_seconds += time.monotonic() - t0
            return self._site_map

    def site_map_text(self) -> str:
        """站点地图的紧凑文本形式（进 planner 提示词）。"""
        sm = self.site_map()
        lines = []
        for group, label in (("console", "控制台"), ("site", "前台")):
            entries = sm.get(group) or []
            if not entries:
                continue
            lines.append(f"## {label}导航")
            for e in entries:
                lines.append(f"- {e['text']} → {e['url']}")
        return "\n".join(lines) or "(站点地图为空)"

    # ------------------------------------------------------------------
    # 页面快照 / 一层展开
    # ------------------------------------------------------------------

    def page_snapshot(self, url: str, max_chars: int = 12000) -> str:
        """用已登录状态打开 url，返回脱敏、截断的文本快照。"""
        self._login_and_save()  # 必须在进入下面的 with sync_playwright() 之前
        t0 = time.monotonic()
        with sync_playwright() as p:
            browser, context = self._new_context(p)
            try:
                page = context.new_page()
                _goto(page, url, self.settings.goto_timeout_ms)
                page.wait_for_timeout(1200)
                snap = redact(text_snapshot(page, max_chars=max_chars), self.settings.secrets)
            except ExplorerError:
                raise
            except Exception as exc:
                raise ExplorerError(f"页面快照失败 {url}: {exc}") from exc
            finally:
                context.close()
                browser.close()
        with self._cost_lock:
            self.explore_seconds += time.monotonic() - t0
        return snap

    def expanded_snapshot(self, url: str, button_name: str, max_chars: int = 12000) -> str:
        """打开 url 后点击**树里存在的**非提交类按钮，再拍快照。

        只做一层展开；点击的按钮必须是页面上真实存在的（否则 ExplorerError），
        且名称不得命中提交类黑名单（只读红线）。
        """
        if is_submit_button(button_name):
            raise ExplorerError(f"拒绝点击提交类按钮: {button_name!r}")
        self._login_and_save()  # 必须在进入下面的 with sync_playwright() 之前
        t0 = time.monotonic()
        with sync_playwright() as p:
            browser, context = self._new_context(p)
            try:
                page = context.new_page()
                _goto(page, url, self.settings.goto_timeout_ms)
                page.wait_for_timeout(1200)
                tree = text_snapshot(page, max_chars=60000)
                if _norm(button_name) not in re.sub(r"\s+", "", tree):
                    # 宽松检查：aria 树里必须能看到这个名字（去空白比对），拒绝盲点
                    raise ExplorerError(
                        f"按钮 {button_name!r} 不在 {url} 的页面树里，拒绝盲点"
                    )
                btn = page.get_by_role("button", name=button_name).first
                if btn.count() == 0:
                    btn = page.get_by_text(button_name, exact=True).first
                btn.click(timeout=self.settings.step_timeout_ms)
                page.wait_for_timeout(1200)  # 等对话框/表单渲染
                snap = redact(text_snapshot(page, max_chars=max_chars), self.settings.secrets)
            except ExplorerError:
                raise
            except Exception as exc:
                raise ExplorerError(f"展开快照失败 {url} @ {button_name!r}: {exc}") from exc
            finally:
                context.close()
                browser.close()
        with self._cost_lock:
            self.explore_seconds += time.monotonic() - t0
        return snap


# --------------------------------------------------------------------------- #
# 辅助（模块级纯函数尽量可测）
# --------------------------------------------------------------------------- #


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _launch(playwright, headless: bool):
    """与 agent.executor.Executor._launch 相同的启动兜底（缺 headless shell 时
    退回 channel=chromium）。"""
    try:
        return playwright.chromium.launch(headless=headless)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) and "headless" in str(exc):
            return playwright.chromium.launch(headless=headless, channel="chromium")
        raise


def _block_external(context, hosts: tuple[str, ...]) -> None:
    if not hosts:
        return
    pattern = re.compile(r"https?://(" + "|".join(re.escape(h) for h in hosts) + r")/")
    context.route(pattern, lambda route: route.abort())


def _goto(page: Page, url: str, timeout_ms: int) -> None:
    if not url.startswith("http://") and not url.startswith("https://"):
        raise ExplorerError(f"非法 URL: {url!r}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as exc:
        raise ExplorerError(f"页面打不开 {url}: {exc}") from exc


def _links_from_aria(tree: str, base_url: str) -> list[dict]:
    """从 aria_snapshot 文本提取链接（"- link "文本"" 行 + 后随 "/url: ..." 行）。

    纯函数（fixture 可测）：相对 URL 拼 base_url，只保留站内、跳过空文本与
    登出链接、按 URL 去重并排序。
    """
    raw: dict[str, dict] = {}
    current_text = None
    for line in tree.splitlines():
        m = _LINK_LINE_RE.match(line)
        if m:
            current_text = m.group(1).strip()
            continue
        m = _URL_LINE_RE.match(line)
        if m and current_text:
            raw.setdefault(m.group(1), {"text": current_text, "url": m.group(1)})
            current_text = None
    links: dict[str, dict] = {}
    for entry in raw.values():
        url = entry["url"]
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        if not url.startswith(base_url):
            continue  # 只保留站内
        text = entry["text"].strip()
        if not text or text in ("登录", "退出登录", "注销"):
            continue
        links.setdefault(url.split("#")[0], {"text": text[:60], "url": url.split("#")[0]})
    return sorted(links.values(), key=lambda l: l["url"])


def _console_menu_links_by_click(page: Page, base_url: str) -> list[dict]:
    """点击侧边栏菜单项、读取跳转后的 URL——第三条自动发现路径。

    实测 Halo 2.20 控制台侧边栏用 `<li class="menu-item">` + Vue Router 渲染，
    没有真实 `<a href>`，aria_snapshot 里这些条目也只是 `listitem` 角色、不带
    `/url:`（都验证过）：aria 与 DOM href 两条路径在控制台页面上都拿不到真实
    路由。退而求其次——点击菜单项、读跳转后的 `page.url`，仍然是**自动发现**
    （不读任何写死的路由表，只读页面本身），且只读（点击只是路由跳转/GET，
    不创建、修改、删除任何数据）。侧边栏在响应式布局下会重复渲染同一份菜单
    （移动端/桌面端两份 DOM），按文本去重只点第一次出现的那个；点不到的项
    （禁用、需要更高权限等）跳过，不阻断整体探索。
    """
    locator = page.locator("li.menu-item .menu-title")
    try:
        n = locator.count()
    except Exception:  # noqa: BLE001 —— 页面没有这个结构（非控制台页）直接跳过
        return []
    seen_text: set[str] = set()
    out: dict[str, dict] = {}
    for i in range(n):
        item = locator.nth(i)
        try:
            text = (item.text_content() or "").strip()
        except Exception:  # noqa: BLE001, S112
            continue
        if not text or text in seen_text:
            continue
        seen_text.add(text)
        try:
            item.click(timeout=3000)
            page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001, S112 —— 点不到就跳过，不让一个菜单项拖垮整体探索
            continue
        url = page.url.split("#")[0]
        if url.startswith(base_url):
            out.setdefault(url, {"text": text[:60], "url": url})
    return sorted(out.values(), key=lambda l: l["url"])


def _extract_links(page: Page, base_url: str) -> list[dict]:
    """从当前页面提取链接（文本 → 绝对 URL）。

    优先 aria_snapshot 的 `/url:` 行（任务书指定），拿不到再退 DOM href；
    最后总是叠加一次点击式发现（见 `_console_menu_links_by_click`）——控制台
    侧边栏没有真实链接，前两条策略拿到的东西不完整但非空（比如页头的
    "查看全部"/"访问首页"），不会触发"结果为空才兜底"的分支，所以点击式
    发现必须总是跑一遍，按 URL 去重合并（不覆盖已发现的）。在没有侧边栏结构
    的页面（如前台首页）上，点击式发现只是 no-op。
    """
    try:
        links = _links_from_aria(page.locator("body").aria_snapshot(), base_url)
    except Exception:  # noqa: BLE001 —— aria 不可用走 DOM 兜底
        links = []
    if not links:
        # DOM 兜底后复用同一套归一/过滤（构造伪树最简单：直接走同样的清洗）
        rows = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => ({text: (e.textContent || '').trim(), href: e.href}))"
        )
        pseudo = "\n".join(
            f'- link "{r["text"]}":\n  - /url: {r["href"]}'
            for r in rows if r["text"] and r["href"]
        )
        links = _links_from_aria(pseudo, base_url)
    click_links = _console_menu_links_by_click(page, base_url)
    if click_links:
        merged = {link["url"]: link for link in links}
        for link in click_links:
            merged.setdefault(link["url"], link)
        links = sorted(merged.values(), key=lambda l: l["url"])
    return links
