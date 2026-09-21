"""Playwright 执行器：把受限动作集用例 JSON 翻译成浏览器操作。

定位策略（任务包要求 role/label/text 优先，其次 CSS）：
- role=button[name="发布"]  -> page.get_by_role(...)
- label=用户名              -> page.get_by_label(...)
- text=发布                 -> page.get_by_text(...)
- placeholder=搜索          -> page.get_by_placeholder(...)
- testid=xxx                -> page.get_by_test_id(...)
- 其他                      -> page.locator(css)

失败三分类口径（每一步失败必须归入其一）：
- assert_failed : assert_* 步骤未通过（断言失败，含断言动作超时未满足）
- locator_failed: click/fill/select 在超时内没有找到目标元素，或选择器表达式无法解析
- timeout       : wait_for 等待超时、goto 页面加载超时、元素已找到但动作未在期限内完成
其他未预期异常一律归入 locator_failed，并保留原始报错文本（口径在 docs/design.md 展开）。

凭据安全：用例里的 {{ADMIN_PASSWORD}} 等占位符只在内存中渲染；
快照/日志/报告落盘前统一 redact，报告中步骤参数保留占位符原文。
"""

from __future__ import annotations

from __future__ import annotations

import fnmatch
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PWError
from playwright.sync_api import Locator, Page, TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from .config import Settings
from .schema import ASSERT_ACTIONS, Case, Step
from .snapshot import numbered, redact, text_snapshot

FAILURE_CLASSES = ("locator_failed", "timeout", "assert_failed")

_TEMPLATE_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_ROLE_RE = re.compile(r'^role=([a-z][a-z0-9_-]*)(?:\[name="([^"]+)"\])?$')


class StepFailure(Exception):
    def __init__(self, failure_class: str, message: str) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message


@dataclass
class StepResult:
    index: int  # 1-based
    action: str
    params: dict[str, str]  # 占位符原文（不渲染，防泄密）
    status: str = "pending"  # passed | failed | skipped（_run_step 内必定覆写）
    failure_class: str | None = None
    error: str | None = None
    elapsed_ms: int = 0
    screenshot: str | None = None
    url_after: str | None = None
    snapshot: str | None = None  # 该步之后的页面文本快照（已脱敏）

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "action": self.action,
            "params": self.params,
            "status": self.status,
            "failure_class": self.failure_class,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "screenshot": self.screenshot,
            "url_after": self.url_after,
            "snapshot": self.snapshot,
        }


@dataclass
class ExecutionResult:
    case_id: str
    started_at: str
    finished_at: str
    final_url: str
    steps: list[StepResult] = field(default_factory=list)
    final_snapshot_numbered: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "final_url": self.final_url,
            "steps": [s.to_dict() for s in self.steps],
            "final_snapshot_numbered": self.final_snapshot_numbered,
            "notes": self.notes,
        }

    @property
    def failed_step(self) -> StepResult | None:
        for s in self.steps:
            if s.status == "failed":
                return s
        return None


# --------------------------------------------------------------------------- #


def render_template(value: str, variables: dict[str, str]) -> str:
    """把 {{VAR}} 渲染成真实值（只在内存中，落盘前用 redact 还原保护）。"""

    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in variables:
            raise StepFailure("locator_failed", f"未知模板变量 {match.group(0)}")
        return variables[key]

    return _TEMPLATE_RE.sub(sub, value)


def _resolve_single(scope: "Page | Locator", expr: str) -> tuple[Locator, str]:
    """在一个作用域（page 或 locator）上解析单个选择器表达式。"""
    m = _ROLE_RE.match(expr)
    if m:
        role, name = m.group(1), m.group(2)
        loc = scope.get_by_role(role, name=name) if name else scope.get_by_role(role)
        return loc, "role"
    for prefix, fn in (
        ("label=", scope.get_by_label),
        ("text=", scope.get_by_text),
        ("placeholder=", scope.get_by_placeholder),
        ("testid=", scope.get_by_test_id),
    ):
        if expr.startswith(prefix):
            return fn(expr[len(prefix) :]), prefix[:-1]
    if expr.startswith(("css=", "xpath=", "//")):
        engine = "xpath" if expr.startswith(("xpath=", "//")) else "css"
        sel = expr.split("=", 1)[1] if expr.startswith(("css=", "xpath=")) else expr
        return scope.locator(sel), engine
    return scope.locator(expr), "css"


def resolve_locator(page: Page, selector: str) -> tuple[Locator, str]:
    """语义选择器 -> Playwright 定位器；支持 `>>` 链式作用域，如
    role=dialog >> role=button[name="发布"]（同名按钮需限定在对话框内）。
    返回 (locator, engine)，engine 为首段引擎；解析失败抛 ValueError。"""
    if " >> " in selector:
        parts = [p for p in (p.strip() for p in selector.split(" >> ")) if p]
        loc, engine = _resolve_single(page, parts[0])
        for part in parts[1:]:
            loc, _sub = _resolve_single(loc, part)
        return loc, engine + "-chain"
    return _resolve_single(page, selector)


class Executor:
    def __init__(self, settings: Settings, run_dir: Path) -> None:
        self.settings = settings
        self.run_dir = Path(run_dir)
        self.shots_dir = self.run_dir / "shots"
        self.shots_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _launch(playwright, headless: bool):
        """启动 chromium。默认优先常规 headless；若本机只装了完整版 Chrome for
        Testing（headless shell 变体缺失，网络受限环境常见），退回 channel=chromium
        的 new-headless 模式。"""
        try:
            return playwright.chromium.launch(headless=headless)
        except Exception as exc:  # noqa: BLE001 —— 仅对可执行文件缺失做回退
            if "Executable doesn't exist" in str(exc) and "headless" in str(exc):
                return playwright.chromium.launch(headless=headless, channel="chromium")
            raise

    # ------------------------------------------------------------------ #

    def _block_external(self, context) -> None:
        """屏蔽被测应用的外联（如 Halo 的版本检查 release-checker.halo.run）。

        目的：这些第三方调用是否成功取决于外部网络，会让"新版本可用"横幅等
        UI 元素时有时无，直接造成用例 flaky（横幅浮层会盖住发布按钮）。
        屏蔽是 e2e 常规做法：被测功能与外联无关，拦截清单可由
        BLOCK_EXTERNAL_HOSTS 配置（留空关闭）。
        """
        hosts = self.settings.blocked_hosts
        if not hosts:
            return
        pattern = re.compile(
            r"https?://(" + "|".join(re.escape(h) for h in hosts) + r")/"
        )
        context.route(pattern, lambda route: route.abort())

    def run_case(self, case: Case) -> ExecutionResult:
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result = ExecutionResult(
            case_id=case.id, started_at=started, finished_at=started, final_url=""
        )
        variables = self.settings.template_vars()

        with sync_playwright() as p:
            browser = self._launch(p, self.settings.headless)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
            self._block_external(context)
            page = context.new_page()
            try:
                for idx, step in enumerate(case.steps, start=1):
                    step_result = self._run_step(page, case, step, idx, variables)
                    result.steps.append(step_result)
                    if step_result.status == "failed":
                        for rest in case.steps[idx:]:
                            result.steps.append(
                                StepResult(
                                    index=case.steps.index(rest) + 1,
                                    action=rest.action,
                                    params=rest.params(),
                                    status="skipped",
                                )
                            )
                        break
                try:
                    result.final_url = page.url
                    result.final_snapshot_numbered = numbered(
                        redact(text_snapshot(page), self.settings.secrets)
                    )
                except PWError as exc:  # 页面已经崩掉时保底
                    result.notes.append(f"最终快照获取失败: {exc}")
            finally:
                context.close()
                browser.close()

        result.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return result

    # ------------------------------------------------------------------ #

    def _run_step(
        self,
        page: Page,
        case: Case,
        step: Step,
        index: int,
        variables: dict[str, str],
    ) -> StepResult:
        sr = StepResult(index=index, action=step.action, params=step.params())
        timeout_ms = step.timeout_ms or (
            self.settings.goto_timeout_ms if step.action == "goto" else self.settings.step_timeout_ms
        )
        t0 = time.monotonic()
        try:
            detail = self._dispatch(page, step, variables, timeout_ms)
            sr.status = "passed"
            sr.error = detail or None
        except StepFailure as exc:
            sr.status = "failed"
            sr.failure_class = exc.failure_class
            sr.error = redact(exc.message, self.settings.secrets)
        except PWTimeoutError as exc:  # 兜底：dispatch 内部应已转换，防御遗漏
            sr.status = "failed"
            sr.failure_class = "timeout"
            sr.error = redact(f"TimeoutError: {exc}", self.settings.secrets)
        except PWError as exc:
            sr.status = "failed"
            sr.failure_class = "locator_failed"
            sr.error = redact(f"PlaywrightError: {exc}", self.settings.secrets)
        except Exception as exc:  # noqa: BLE001 —— 未预期异常也要落到三分类之一
            sr.status = "failed"
            sr.failure_class = "locator_failed"
            sr.error = redact(f"{type(exc).__name__}: {exc}", self.settings.secrets)
        sr.elapsed_ms = int((time.monotonic() - t0) * 1000)

        # 失败必须留截图；成功也留一张（体积小，便于复核）
        sr.screenshot = self._shot(page, case.id, index, sr.status)
        try:
            sr.url_after = page.url
            sr.snapshot = redact(text_snapshot(page, max_chars=6000), self.settings.secrets)
        except PWError:
            sr.snapshot = None
        return sr

    def _dispatch(
        self, page: Page, step: Step, variables: dict[str, str], timeout_ms: int
    ) -> str | None:
        """执行单个动作。失败统一抛 StepFailure（带三分类），成功返回备注或 None。"""
        action = step.action

        if action == "goto":
            url = render_template(step.url or "", variables)
            try:
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            except PWTimeoutError as exc:
                raise StepFailure("timeout", f"页面加载超时({timeout_ms}ms): {url}; {exc}") from exc
            except PWError as exc:
                raise StepFailure("timeout", f"页面加载失败: {url}; {exc}") from exc
            return None

        if action == "wait_for":
            try:
                if step.selector:
                    loc, _engine = resolve_locator(page, render_template(step.selector, variables))
                    loc.wait_for(state="visible", timeout=timeout_ms)
                else:
                    page.get_by_text(render_template(step.text or "", variables)).first.wait_for(
                        state="visible", timeout=timeout_ms
                    )
            except PWTimeoutError as exc:
                raise StepFailure(
                    "timeout",
                    f"等待超时({timeout_ms}ms): selector={step.selector!r} text={step.text!r}; {exc}",
                ) from exc
            return None

        # ---- 交互动作：click / fill / select ----
        if action in ("click", "fill", "select"):
            raw_selector = render_template(step.selector or "", variables)
            try:
                loc, engine = resolve_locator(page, raw_selector)
            except ValueError as exc:
                raise StepFailure("locator_failed", str(exc)) from exc
            try:
                if action == "click":
                    loc.click(timeout=timeout_ms)
                elif action == "fill":
                    loc.fill(render_template(step.value or "", variables), timeout=timeout_ms)
                else:  # select
                    value = render_template(step.value or "", variables)
                    try:
                        loc.select_option(value, timeout=timeout_ms)
                    except PWTimeoutError:
                        # 按 value 选不中再按 label 选（select 用例常见 label/值不一致）
                        loc.select_option(label=value, timeout=timeout_ms)
            except PWTimeoutError as exc:
                if loc.count() == 0:
                    raise StepFailure(
                        "locator_failed",
                        f"定位失败({timeout_ms}ms 内未找到元素): engine={engine} selector={step.selector!r}",
                    ) from exc
                raise StepFailure(
                    "timeout",
                    f"动作超时({timeout_ms}ms，元素已找到但未完成): engine={engine} "
                    f"selector={step.selector!r}; {exc}",
                ) from exc
            return None

        # ---- 断言动作：assert_* ----
        if action == "assert_text":
            try:
                expected_text = render_template(step.text or "", variables)
                if step.selector:
                    raw_selector = render_template(step.selector, variables)
                    loc, _engine = resolve_locator(page, raw_selector)
                    loc.filter(has_text=render_template(step.text, variables)).first.wait_for(
                        state="visible", timeout=timeout_ms
                    )
                else:
                    page.get_by_text(expected_text).first.wait_for(
                        state="visible", timeout=timeout_ms
                    )
            except PWTimeoutError as exc:
                raise StepFailure(
                    "assert_failed",
                    f"断言失败: 期望文本 {step.text!r} 未出现（selector={step.selector!r}, {timeout_ms}ms）",
                ) from exc
            return None

        if action == "assert_visible":
            raw_selector = render_template(step.selector or "", variables)
            try:
                loc, engine = resolve_locator(page, raw_selector)
                loc.first.wait_for(state="visible", timeout=timeout_ms)
            except PWTimeoutError as exc:
                raise StepFailure(
                    "assert_failed",
                    f"断言失败: 元素不可见 selector={step.selector!r}（{timeout_ms}ms）",
                ) from exc
            except ValueError as exc:
                raise StepFailure("locator_failed", str(exc)) from exc
            return None

        if action == "assert_url":
            expected = render_template(step.url or "", variables)

            def _url_ok(current: str) -> bool:
                return (
                    fnmatch.fnmatch(current, expected)
                    if any(c in expected for c in "*?[")
                    else expected in current
                )

            # URL 断言必须轮询等待：登录/跳转是异步的，立即读 page.url 有竞态
            deadline = time.monotonic() + timeout_ms / 1000
            current = page.url
            while not _url_ok(current):
                if time.monotonic() >= deadline:
                    raise StepFailure(
                        "assert_failed",
                        f"断言失败: 期望 URL 包含/匹配 {expected!r}，实际 {current!r}（等待 {timeout_ms}ms）",
                    )
                page.wait_for_timeout(200)
                current = page.url
            return None

        raise StepFailure("locator_failed", f"未知动作: {action}")  # schema 层已拦截，防御性兜底

    # ------------------------------------------------------------------ #

    def _shot(self, page: Page, case_id: str, index: int, status: str) -> str | None:
        try:
            path = self.shots_dir / f"{case_id}-step{index:02d}-{status}.png"
            page.screenshot(path=str(path), full_page=False)
            return str(path)
        except PWError:
            return None
