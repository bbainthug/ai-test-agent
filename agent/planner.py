"""Planner：功能描述（一句话）-> LLM -> 结构化用例 JSON（受限动作集）。

输出被 agent.schema.Case 严格校验；首次输出不合法时，
把校验错误回传给模型修复一次（记录在 calls.jsonl，成本可复盘）。
仍然失败则抛 PlannerError，绝不把非法用例交给执行器。
"""

from __future__ import annotations

import argparse
import json
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

## 系统事实（Halo 2.20 实测）
- 前台首页: http://localhost:8090/
- 控制台: http://localhost:8090/console/（登录后落地 /console/dashboard）
- 登录页: http://localhost:8090/login（字段：用户名、密码；按钮文本"登录"）
- 重要：登录成功后浏览器先跳到个人中心 /uc/profile，并不会直接进控制台；
  要测控制台内功能，必须在登录步骤之后单独 goto 控制台地址。
  不要在"登录"这一步之后直接断言 /console/dashboard。
- 文章编辑器: http://localhost:8090/console/posts/editor（标题输入框 name 为"请输入标题"；
  正文为 contenteditable 区域；点"发布"后弹出"文章设置"对话框，需在对话框内再点"发布"）
- 文章列表: http://localhost:8090/console/posts
- 站点设置: http://localhost:8090/console/settings（含"站点标题"输入框与"保存"按钮）
- 管理员凭据是机密，用户名一律写 {{ADMIN_USER}}，密码一律写 {{ADMIN_PASSWORD}}，禁止编造真实凭据。
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
- wait_for / assert_text 的 text 只能写你从"系统事实"里确认会渲染在页面上的文本；
  想不出确定存在的文本就不要用文本等待，改用 URL 或元素断言。
- 凭据只能用 {{ADMIN_USER}} / {{ADMIN_PASSWORD}} 占位符。
"""

ALLOWED_ACTIONS_PROMPT = "、".join(ACTIONS)


class PlannerError(RuntimeError):
    """两轮规划后仍无法产出合法用例。"""


def plan_case(
    client: LLMClient,
    *,
    feature_desc: str,
    feature_id: str,
    max_rounds: int = 2,
) -> Case:
    """生成并校验一条用例。失败时带校验错误重试（max_rounds 次）。"""
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent.planner",
        description="功能描述 -> LLM 生成结构化用例 JSON（受限动作集）",
    )
    parser.add_argument("--feature", required=True, help="一句话功能描述")
    parser.add_argument("--feature-id", required=True, help="feature 编号，如 login")
    parser.add_argument("--out", required=True, help="生成的用例 JSON 输出路径")
    parser.add_argument("--run-dir", required=True, help="run 目录（LLM 调用审计写入其中的 calls.jsonl）")
    args = parser.parse_args(argv)

    from .config import load_settings
    from .llm import LLMError

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
    case = plan_case(client, feature_desc=args.feature, feature_id=args.feature_id)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(case.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"用例已生成: {out}（steps={len(case.steps)}, expected={len(case.expected)}）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PlannerError, LLMError) as exc:  # noqa: F821 —— 延迟导入的 LLMError
        print(f"[planner] 失败: {exc}")
        raise SystemExit(2)
