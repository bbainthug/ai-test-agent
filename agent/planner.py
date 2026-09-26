"""Planner：功能描述（一句话）-> LLM -> 结构化用例 JSON（受限动作集）。

两种模式（B2）：
- baseline：与旧版一致，凭"系统事实"提示词生成——不再默认；
- grounded（默认）：先用 Explorer 自动探索真实页面（站点地图 + 目标页面
  可访问性树），两步生成（选页面 → 写用例），再做**静态选择器校验**：
  用例里每个 role=/label=/text= 选择器必须能在目标页面快照里找到匹配
  （role 的 name 精确匹配，避免"保存"子串匹配到"保存并继续添加"）；
  违例把具体问题回传 LLM 修一次，仍不过则照常交给执行器但在 grounding
  记录里标 violations。探索失败时降级 baseline 并记录 fallback，不静默。

输出被 agent.schema.Case 严格校验；首次输出不合法时，
把校验错误回传给模型修复一次（记录在 calls.jsonl，成本可复盘）。
仍然失败则抛 PlannerError，绝不把非法用例交给执行器。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pydantic import ValidationError

from .llm import LLMClient, LLMError
from .schema import ACTIONS, Case

PLANNER_SYSTEM_PROMPT = """你是资深测试工程师，为开源建站系统 Halo（本地运行）生成 e2e 自动化用例。

## 受限动作集（steps 里只能用这 8 个动作，禁止自由文本步骤）
- goto:      {"action": "goto", "url": "http://localhost:8090/"}
- click:     {"action": "click", "selector": "..."}
- fill:      {"action": "fill", "selector": "...", "value": "..."}
- select:    {"action": "select", "selector": "...", "value": "..."}
- wait_for:  {"action": "wait_for", "selector": "..."} 或 {"action": "wait_for", "text": "..."}
- assert_text:    {"action": "assert_text", "text": "..."} 或加 "selector" 限定范围
- assert_visible: {"action": "assert_visible", "selector": "..."}
- assert_url:     {"action": "assert_url", "url": "..."}

## 选择器写法（优先级从高到低）
role=button[name="发布"] > label=用户名 > text=发布 > placeholder=搜索 > 普通 CSS
- role 的 name 属性必须写界面上真实显示的中文文本（本系统为简体中文界面）。
- 优先用语义选择器；CSS 只在语义定位不可行时使用。

## 系统事实（Halo 2.20 实测，通用规则）
- 前台首页: http://localhost:8090/
- 控制台: http://localhost:8090/console/（登录后落地 /console/dashboard）
- 登录页: http://localhost:8090/login（字段：用户名、密码；按钮文本"登录"）
- 文章编辑器: http://localhost:8090/console/posts/editor（标题输入框 name 为"请输入标题"；
  正文为 contenteditable 区域；点"发布"后弹出"文章设置"对话框，需在对话框内再点"发布"）
- 文章列表: http://localhost:8090/console/posts
- 站点设置: http://localhost:8090/console/settings（含"站点标题"输入框与"保存"按钮）
- 重要：登录成功后浏览器先跳到个人中心 /uc/profile，并不会直接进控制台；
  要测控制台内功能，必须在登录步骤之后单独 goto 控制台地址。
  不要在"登录"这一步之后直接断言 /console/dashboard。
- 管理员凭据是机密，用户名一律写 {{ADMIN_USER}}，密码一律写 {{ADMIN_PASSWORD}}，禁止编造真实凭据。
- 新建的数据（分类、标签、文章等）名称和别名要带 {{RUN_ID}}（每次执行唯一，如 "测试分类-{{RUN_ID}}"），
  否则重复执行会因"已存在"失败；断言时同样写带 {{RUN_ID}} 的名称。
- 断言入口 URL 时用子串（如 /console/dashboard），不要写完整带参数的地址。

## 输出格式
只输出一个 JSON 对象（不要 markdown 围栏、不要解释文字）：
{
  "id": "小写字母数字连字符，<=64字符",
  "feature_id": "功能编号，与输入一致",
  "title": "用例标题（中文）",
  "priority": "P0|P1|P2",
  "preconditions": ["前置条件（中文）"],
  "steps": [ {"action": "...", ...}, ... ],
  "expected": ["可观察的预期结果（中文，必须能在页面文本快照中验证）"]
}
注意：expected 必须是页面上可验证的现象（文本出现、元素可见、URL 变化），不要写"数据库正确"这类无法从 UI 验证的预期。

## 稳定性红线（违反=用例作废）
- 跳转断言一律优先 assert_url（用子串，如 /uc/profile）；URL 能证明的事不要用文本断言。
- wait_for / assert_text 的 text 只能写你确认会渲染在页面上的文本（grounded 模式下来自快照）；
  想不出确定存在的文本就不要用文本等待，改用 URL 或元素断言。
- 凭据只能用 {{ADMIN_USER}} / {{ADMIN_PASSWORD}} 占位符。
"""

# grounded 模式下的"通用事实"提示词：去掉 baseline 里页面具体的 URL/控件事实
# （编辑器地址、站点设置控件等），页面事实一律来自探索到的真实快照。
GROUND_COMMON_FACTS = """## 系统事实（通用规则）
- 登录页: http://localhost:8090/login（字段：用户名、密码；按钮文本"登录"）。
  登录成功后浏览器先跳到个人中心 /uc/profile，并不会直接进控制台；
  要测控制台内功能，必须在登录步骤之后单独 goto 目标页面地址。
- 管理员凭据是机密，用户名一律写 {{ADMIN_USER}}，密码一律写 {{ADMIN_PASSWORD}}，禁止编造真实凭据。
- 新建的数据（分类、标签、文章等）名称和别名要带 {{RUN_ID}}（每次执行唯一，如 "测试分类-{{RUN_ID}}"），
  否则重复执行会因"已存在"失败；断言时同样写带 {{RUN_ID}} 的名称。
- 断言入口 URL 时用子串（如 /uc/profile），不要写完整带参数的地址。
- 所有路由与控件文案只能来自下面给的站点地图与页面快照，禁止编造。

## 输出格式
只输出一个 JSON 对象（不要 markdown 围栏、不要解释文字）：
{
  "id": "小写字母数字连字符，<=64字符",
  "feature_id": "功能编号，与输入一致",
  "title": "用例标题（中文）",
  "priority": "P0|P1|P2",
  "preconditions": ["前置条件（中文）"],
  "steps": [ {"action": "...", ...}, ... ],
  "expected": ["可观察的预期结果（中文，必须能在页面文本快照中验证）"]
}

## 稳定性红线（违反=用例作废）
- 跳转断言一律优先 assert_url（用子串）；URL 能证明的事不要用文本断言。
- wait_for / assert_text 的 text 只能写快照里确认存在的文本；
  想不出确定存在的文本就不要用文本等待，改用 URL 或元素断言。
- 凭据只能用 {{ADMIN_USER}} / {{ADMIN_PASSWORD}} 占位符。
"""

SELECT_PAGE_SYSTEM_PROMPT = """你是测试工程师。下面是一个开源建站系统（Halo，本地运行）控制台与前台的
导航链接站点地图（自动探索真实页面得到）。给定要测的功能描述，选出最合适的目标页面。

只输出一个 JSON 对象（不要 markdown 围栏、不要解释文字）：
{
  "url": "目标页面 URL，必须是站点地图里的 URL（或在其基础上增加路径参数，并在 reason 里说明）",
  "reason": "为什么选这个页面",
  "expand_click": null 或 "按钮名"
}
- expand_click：仅当目标页面上的功能藏在某个按钮后面（如"新建"对话框）时，
  写该按钮在页面上显示的名字；否则写 null。
- 禁止选择会直接提交/修改数据的操作；你只负责选页面，不写用例步骤。
"""

ALLOWED_ACTIONS_PROMPT = "、".join(ACTIONS)

VIOLATION_HINT = "请修正用例：只使用目标页面快照里真实存在的选择器与文案，重新输出完整 JSON 用例。"


class PlannerError(RuntimeError):
    """两轮规划后仍无法产出合法用例。"""


# --------------------------------------------------------------------------- #
# 静态选择器校验（纯函数，不跑浏览器）
# --------------------------------------------------------------------------- #

_ROLE_NAME_RE = re.compile(r'^role=([a-z][a-z0-9_-]*)(?:\[name="([^"]*)"\])?$')
_PREFIXES = ("label=", "text=", "placeholder=", "css=", "xpath=", "testid=")
_SKIP_PREFIXES = ("css=", "xpath=", "placeholder=", "testid=")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def parse_snapshot_entries(snapshot: str) -> list[tuple[str, str]]:
    """把 aria 快照解析成 (role, name) 条目列表（name 已归一空白）。

    兼容 `- button "发布"` / `- button "发布":` / `- dialog:`（无名字）等行。
    """
    entries: list[tuple[str, str]] = []
    for line in snapshot.splitlines():
        m = re.match(r'^\s*-\s+([a-z][a-z0-9_-]+)(?:\s+"([^"]*)")?\s*:?\s*$', line)
        if m:
            entries.append((m.group(1), _norm(m.group(2) or "")))
    return entries


def _selector_parts(selector: str) -> list[str]:
    if " >> " in selector:
        return [p.strip() for p in selector.split(" >> ") if p.strip()]
    return [selector.strip()]


def _check_part(part: str, entries: list[tuple[str, str]], full_text: str) -> str | None:
    """校验单个选择器片段。返回 None=通过，否则返回违例描述。"""
    if part.startswith(_SKIP_PREFIXES):
        return None  # CSS/xpath/placeholder/testid 无法从 aria 树可靠判断，跳过校验
    m = _ROLE_NAME_RE.match(part)
    if m:
        role, name = m.group(1), m.group(2) or ""
        role_norm = _norm(role)
        if name:
            want = _norm(name)
            if any(r == role_norm and n == want for r, n in entries):
                return None
            near = sorted({f'{r} "{n}"' for r, n in entries if r == role_norm and n})[:5]
            near_hint = f"；快照中该角色的名字有: {near}" if near else ""
            return f'{part}: 快照中不存在 name 精确等于 "{name}" 的 {role}{near_hint}（子串不算）'
        if any(r == role_norm for r, _ in entries):
            return None
        return f"{part}: 快照中不存在该角色的元素"
    for prefix, kind in (("label=", "label"), ("text=", "text")):
        if part.startswith(prefix):
            want = _norm(part[len(prefix):])
            if not want:
                return f"{part}: 空匹配文本"
            if want in full_text:
                return None
            return f'{part}: 快照文本中找不到 "{part[len(prefix):]}"'
    return None  # 未知写法不拦


def validate_selectors(case: Case, snapshot: str) -> list[str]:
    """校验用例里的语义选择器能否在目标页面快照中找到。返回违例描述列表。

    登录段（goto /login 之后、下一个 goto 之前）不校验：登录页控件不在
    目标页面快照里，由"通用事实"提示词保证（探索器登录后 /login 会重定向，
    无法单独取快照）。
    """
    entries = parse_snapshot_entries(snapshot)
    full_text = re.sub(r"\s+", "", snapshot)
    violations: list[str] = []
    in_login = False
    for idx, step in enumerate(case.steps, start=1):
        if step.action == "goto" and step.url:
            in_login = step.url.rstrip("/").endswith("/login")
            continue
        if in_login:
            continue
        selector = step.selector or ""
        text = step.text or ""
        if selector and not selector.startswith(("css=", "xpath=", "//", "testid=")):
            for part in _selector_parts(selector):
                problem = _check_part(part, entries, full_text)
                if problem:
                    violations.append(f"步骤{idx} {step.action}: {problem}")
        if step.action == "wait_for" and text and _norm(text) not in full_text:
            violations.append(f"步骤{idx} wait_for: 快照文本中找不到 \"{text}\"")
    return violations


# --------------------------------------------------------------------------- #
# 规划入口
# --------------------------------------------------------------------------- #


def _plan_baseline(client: LLMClient, *, feature_desc: str, feature_id: str,
                   max_rounds: int) -> Case:
    user_prompt = (
        f"功能编号: {feature_id}\n功能描述: {feature_desc}\n"
        f"允许的动作只有: {ALLOWED_ACTIONS_PROMPT}。请输出 JSON 用例。"
    )
    last_error = ""
    for round_no in range(1, max_rounds + 1):
        prompt = user_prompt
        if last_error:
            prompt = (
                f"{user_prompt}\n\n你上一轮输出的用例未通过 schema 校验，错误如下，请修正后重新输出完整 JSON：\n"
                f"{last_error}"
            )
        raw = client.chat_json(
            phase=f"plan:r{round_no}", system=PLANNER_SYSTEM_PROMPT, user=prompt
        )
        try:
            return Case.model_validate(raw)
        except ValidationError as exc:
            last_error = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )[:800]
    raise PlannerError(f"feature {feature_id}: {max_rounds} 轮规划均未产出合法用例，最后错误: {last_error}")


def _write_case_with_snapshot(client: LLMClient, *, feature_desc: str, feature_id: str,
                              snapshot: str, site_map_note: str, max_rounds: int) -> Case:
    """grounded 第二步：功能描述 + 目标页面快照 -> 用例（schema 校验重试）。"""
    system = (
        "你是资深测试工程师，为开源建站系统 Halo（本地运行，简体中文界面）生成 e2e 自动化用例。\n\n"
        f"## 受限动作集（steps 里只能用这 {len(ACTIONS)} 个动作，禁止自由文本步骤）\n"
        "- goto:      {\"action\": \"goto\", \"url\": \"...\"}\n"
        "- click:     {\"action\": \"click\", \"selector\": \"...\"}\n"
        "- fill:      {\"action\": \"fill\", \"selector\": \"...\", \"value\": \"...\"}\n"
        "- select:    {\"action\": \"select\", \"selector\": \"...\", \"value\": \"...\"}\n"
        "- wait_for:  {\"action\": \"wait_for\", \"selector\": \"...\"} 或 {\"action\": \"wait_for\", \"text\": \"...\"}\n"
        "- assert_text:    {\"action\": \"assert_text\", \"text\": \"...\"} 或加 \"selector\" 限定范围\n"
        "- assert_visible: {\"action\": \"assert_visible\", \"selector\": \"...\"}\n"
        "- assert_url:     {\"action\": \"assert_url\", \"url\": \"...\"}\n\n"
        "## 选择器写法（优先级从高到低）\n"
        "role=button[name=\"发布\"] > label=用户名 > text=发布 > placeholder=搜索 > 普通 CSS\n"
        "role 的 name 必须与快照中的名字**完全一致**（逐字，不要截断或拼凑）。\n\n"
        f"{GROUND_COMMON_FACTS}\n\n"
        f"## 站点地图备注\n{site_map_note}\n\n"
        "## 目标页面真实快照（aria 树；选择器与断言文案只能从这里取）\n"
        f"{snapshot}\n"
    )
    user_prompt = (
        f"功能编号: {feature_id}\n功能描述: {feature_desc}\n"
        f"允许的动作只有: {ALLOWED_ACTIONS_PROMPT}。"
        "请只基于上面的快照输出 JSON 用例。"
    )
    last_error = ""
    for round_no in range(1, max_rounds + 1):
        prompt = user_prompt
        if last_error:
            prompt = (
                f"{user_prompt}\n\n你上一轮输出的用例未通过 schema 校验，错误如下，请修正后重新输出完整 JSON：\n"
                f"{last_error}"
            )
        raw = client.chat_json(
            phase=f"plan:grounded:write:r{round_no}", system=system, user=prompt
        )
        try:
            return Case.model_validate(raw)
        except ValidationError as exc:
            last_error = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )[:800]
    raise PlannerError(f"feature {feature_id}: {max_rounds} 轮规划均未产出合法用例，最后错误: {last_error}")


def _select_page(client: LLMClient, *, feature_desc: str, site_map_text: str,
                 max_rounds: int = 2) -> dict:
    """grounded 第一步：功能描述 + 站点地图 -> 目标页面 URL（必须来自站点地图）。"""
    user_prompt = f"功能描述: {feature_desc}\n\n站点地图：\n{site_map_text}\n请输出 JSON。"
    last_error = ""
    for round_no in range(1, max_rounds + 1):
        prompt = user_prompt
        if last_error:
            prompt = f"{prompt}\n\n上一轮输出不合规：{last_error}\n请重新输出 JSON。"
        raw = client.chat_json(
            phase=f"plan:grounded:select:r{round_no}", system=SELECT_PAGE_SYSTEM_PROMPT,
            user=prompt,
        )
        if not isinstance(raw, dict) or not isinstance(raw.get("url"), str) or not raw["url"].strip():
            last_error = "输出必须是含 url 字段的 JSON 对象"
            continue
        urls = {e["url"] for group in ("console", "site")
                for e in _site_map_entries(site_map_text)}
        chosen = raw["url"].strip()
        if chosen not in urls and not any(chosen.startswith(u) for u in urls):
            last_error = f"所选 URL 不在站点地图中: {chosen}"
            continue
        raw["url"] = chosen
        return raw
    raise PlannerError(f"两轮选页均未给出站点地图内的 URL，最后错误: {last_error}")


def _site_map_entries(site_map_text: str) -> list[dict]:
    """从站点地图文本反向取 URL 集合（"- 文本 → url" 行）。"""
    out = []
    for line in site_map_text.splitlines():
        m = re.match(r"^-\s+(.+?)\s+→\s+(\S+)\s*$", line)
        if m:
            out.append({"text": m.group(1), "url": m.group(2)})
    return out


def plan_case(
    client: LLMClient,
    *,
    feature_desc: str,
    feature_id: str,
    max_rounds: int = 2,
    mode: str = "grounded",
    explorer=None,  # agent.explorer.Explorer | None
    grounding: dict | None = None,
) -> Case:
    """生成并校验一条用例。

    mode="grounded"（默认）走两步 grounded 规划 + 静态选择器校验；
    explorer 缺失或探索失败时降级 baseline，并把降级原因写进 grounding
    （调用方传了 grounding dict 才记录——基准与 CLI 都会传）。
    mode="baseline" 保持旧行为。
    返回 Case；grounding 信息通过可变的 grounding dict 带出。
    """
    if mode not in ("baseline", "grounded"):
        raise ValueError(f"未知 planner mode: {mode}")
    g = grounding if grounding is not None else {}

    if mode == "grounded" and explorer is not None:
        import time

        explore_seconds = 0.0  # 只累加下面 3 个 explorer 调用本身的墙钟，不含 LLM 往返
        try:
            t = time.monotonic()
            site_map_text = explorer.site_map_text()
            explore_seconds += time.monotonic() - t

            selection = _select_page(
                client, feature_desc=feature_desc, site_map_text=site_map_text
            )
            url = selection["url"]

            t = time.monotonic()
            snapshot = explorer.page_snapshot(url)
            explore_seconds += time.monotonic() - t

            expand_click = selection.get("expand_click") or None
            if expand_click:
                t = time.monotonic()
                try:
                    expanded = explorer.expanded_snapshot(url, expand_click)
                    snapshot = expanded + "\n" + snapshot
                except Exception as exc:  # noqa: BLE001 —— 展开失败不阻断，退回基础快照
                    g["expand_note"] = f"一层展开失败，退回基础快照: {exc}"
                finally:
                    explore_seconds += time.monotonic() - t
            case = _write_case_with_snapshot(
                client, feature_desc=feature_desc, feature_id=feature_id,
                snapshot=snapshot, site_map_note=site_map_text[:2000], max_rounds=max_rounds,
            )
            violations = validate_selectors(case, snapshot)
            if violations:
                # 把具体违例回传 LLM 修一次
                g["violations"] = violations
                repair_prompt = (
                    f"功能编号: {feature_id}\n功能描述: {feature_desc}\n\n"
                    "你上一轮用例里的以下选择器在目标页面快照中不存在：\n"
                    + "\n".join(f"- {v}" for v in violations)
                    + f"\n\n{VIOLATION_HINT}\n\n目标页面快照：\n{snapshot[:8000]}"
                )
                try:
                    raw = client.chat_json(
                        phase="plan:grounded:repair", system=PLANNER_SYSTEM_PROMPT,
                        user=repair_prompt,
                    )
                    repaired = Case.model_validate(raw)
                    remaining = validate_selectors(repaired, snapshot)
                    if not remaining:
                        g.pop("violations", None)
                    else:
                        g["violations"] = remaining
                    case = repaired
                except (ValidationError, LLMError, ValueError, KeyError, IndexError):
                    # 修复轮失败（输出不合法/调用失败）则保留原 case（violations 已记录）
                    pass
            g.update({
                "status": "ok", "mode": "grounded", "page_url": url,
                "expand_click": expand_click,
                "explore_seconds": round(explore_seconds, 2),
            })
            return case
        except PlannerError:
            raise  # 规划轮次用尽是真失败，不应静默降级重试
        except Exception as exc:  # noqa: BLE001 —— 探索/选页失败一律降级，不许静默
            g.update({
                "status": "fallback", "mode": "baseline", "page_url": None,
                "expand_click": None, "violations": [],
                # 失败可能发生在 explorer 调用内部（已累计部分）或 LLM 选页调用里
                # （explore_seconds 仍是 0）；不用"距 explore_t0 的墙钟"，那会把
                # LLM 选页/写用例的等待也算进探索耗时。
                "explore_seconds": round(explore_seconds, 2),
                "reason": f"grounded 规划失败，降级 baseline: {str(exc)[:200]}",
            })
            return _plan_baseline(client, feature_desc=feature_desc,
                                  feature_id=feature_id, max_rounds=max_rounds)

    if mode == "grounded":
        g.update({
            "status": "fallback", "mode": "baseline", "page_url": None,
            "expand_click": None, "violations": [], "explore_seconds": 0.0,
            "reason": "explorer 不可用，降级 baseline",
        })
    else:
        g.update({"status": "n/a", "mode": "baseline"})
    return _plan_baseline(client, feature_desc=feature_desc,
                          feature_id=feature_id, max_rounds=max_rounds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent.planner",
        description="功能描述 -> LLM 生成结构化用例 JSON（受限动作集）",
    )
    parser.add_argument("--feature", required=True, help="一句话功能描述")
    parser.add_argument("--feature-id", required=True, help="feature 编号，如 login")
    parser.add_argument("--out", required=True, help="生成的用例 JSON 输出路径")
    parser.add_argument("--run-dir", required=True, help="run 目录（LLM 调用审计写入其中的 calls.jsonl）")
    parser.add_argument("--mode", default="grounded", choices=("baseline", "grounded"))
    parser.add_argument("--cache-dir", default=".runtime/explorer",
                        help="探索器缓存目录（storage_state / site_map.json）")
    args = parser.parse_args(argv)

    from .config import load_settings
    from .explorer import Explorer

    settings = load_settings()
    settings.require_llm_config()
    run_dir = Path(args.run_dir)
    client = LLMClient(
        run_id=run_dir.name,
        run_dir=run_dir,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout_s=settings.llm_timeout_s,
    )
    explorer = Explorer(settings, Path(args.cache_dir)) if args.mode == "grounded" else None
    grounding: dict = {}
    case = plan_case(client, feature_desc=args.feature, feature_id=args.feature_id,
                     mode=args.mode, explorer=explorer, grounding=grounding)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(case.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    grounding_path = out.with_suffix(".grounding.json")
    grounding_path.write_text(json.dumps(grounding, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"用例已生成: {out}（steps={len(case.steps)}, expected={len(case.expected)}, "
          f"grounding={grounding.get('status')}）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PlannerError, LLMError) as exc:
        print(f"[planner] 失败: {exc}")
        raise SystemExit(2)
