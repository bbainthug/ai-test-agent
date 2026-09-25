"""LLM-as-Judge：只看文本快照，不看截图；三态判定 pass/fail/unsure。

硬规则：
- unsure 必须存在，不允许二分（证据不足/步骤被跳过/快照无相关信息 -> unsure）；
- 证据必须引用最终快照的行号并摘录原文，防止裁判凭空脑补；
- 输出解析失败/不合 schema 一律降级为 unsure（并标记 parsed=False），
  绝不默认 pass —— 这是控制误报率的第一道闸。
"""

from __future__ import annotations

import json

from .executor import ExecutionResult
from .llm import LLMClient
from .schema import Case

JUDGE_SYSTEM_PROMPT = """你是严格的 e2e 测试执行裁判，判定一条自动化用例在真实系统上是否达到预期。

输入包含：
1. 用例的 expected（预期结果列表）
2. 每一步的执行结果（passed/failed/skipped 与失败分类）
3. 最终页面的文本快照（带 L 行号，来自页面可访问性树）

判定规则（三态，不许二分）：
- pass：每一条 expected 都有明确证据支持（快照中的文本/元素，或成功的断言步骤），且没有任何步骤 failed 或 skipped。
- fail：存在与 expected 明确矛盾的证据——断言步骤失败、页面出现明确错误提示、快照中确认不存在预期文本/元素。
- unsure：以下任一情况必须判 unsure，宁可 unsure 也不得猜测：
  * 有关键步骤 failed 或 skipped，导致后续预期无法证明或证伪；
  * 快照中找不到判断某条 expected 所需的信息，且没有明确反证；
  * 证据相互矛盾或不足以区分"功能坏了"和"页面还没加载完"。

其他要求：
- 只依据给定文本证据判定，禁止想象页面内容，禁止使用测试之外的常识推断系统行为。
- evidence 里每条证据必须给出 snapshot_line（最终快照的行号）和 quote（该行原文摘录）。
- 输出只能是 JSON 对象，不要输出其他文字：
{"verdict": "pass|fail|unsure", "reason": "一句话理由", "evidence": [{"expected_index": 0, "snapshot_line": 12, "quote": "..."}]}
"""

BLIND_JUDGE_SYSTEM_PROMPT = """你是严格的 e2e 测试结果裁判，判定一个功能在真实系统上是否表现符合预期。

你只能看到两样东西：
1. 预期结果列表（expected）
2. 操作结束后最终页面的文本快照（带 L 行号，来自页面可访问性树）

你看不到任何步骤的执行结果，也看不到断言是否通过——只能根据最终页面自己判断。

判定规则（三态，不许二分）：
- pass：每一条 expected 都能在最终快照里找到明确支持的证据。
- fail：快照里有与 expected 明确矛盾的证据（错误提示、失败提示、页面显示了与预期相反的内容、应出现的内容明确没有出现且页面已正常加载）。
- unsure：快照里找不到判断所需的信息且没有明确反证，或页面看起来没有加载完成、停留在无关页面。

其他要求：
- 只依据快照文本判定，禁止想象页面内容，禁止用常识推测系统"应该"做了什么。
- evidence 里每条证据必须给出 snapshot_line（最终快照的行号）和 quote（该行原文摘录）。
- 输出只能是 JSON 对象：
{"verdict": "pass|fail|unsure", "reason": "一句话理由", "evidence": [{"expected_index": 0, "snapshot_line": 12, "quote": "..."}]}
"""

JUDGE_MODES = ("informed", "blind")

VALID_VERDICTS = ("pass", "fail", "unsure")


def judge_execution(
    client: LLMClient,
    case: Case,
    exec_result: ExecutionResult,
    max_snapshot_lines: int = 400,
    mode: str = "informed",
) -> dict:
    """裁判一次执行。返回 {verdict, reason, evidence, parsed, mode}。

    mode:
    - informed：能看到每一步的执行结果（默认，阶段 A 口径）；
    - blind：只看 expected + 最终快照，看不到步骤是否通过——用于衡量裁判是否只是在复述断言结果。
    """
    if mode not in JUDGE_MODES:
        raise ValueError(f"未知裁判模式 {mode!r}，可选 {JUDGE_MODES}")
    if mode == "blind":
        return _judge_blind(client, case, exec_result, max_snapshot_lines)
    steps_desc = []
    for s in exec_result.steps:
        line = f"步骤{s.index} [{s.action}] {json.dumps(s.params, ensure_ascii=False)} -> {s.status}"
        if s.failure_class:
            line += f"（失败分类: {s.failure_class}）"
        if s.error:
            line += f"; 报错: {s.error}"
        steps_desc.append(line)

    user_prompt = f"""# 用例
id: {case.id}
title: {case.title}

# expected
{chr(10).join(f"{i}. {e}" for i, e in enumerate(case.expected))}

# 执行步骤结果
{chr(10).join(steps_desc) or "(无步骤执行结果)"}

# 最终页面文本快照（含行号）
{exec_result.final_snapshot_numbered or "(最终快照为空)"}

请按系统提示的三态规则输出 JSON 判定。"""
    # 截断超长快照，控制裁判成本
    lines = user_prompt.splitlines()
    if len(lines) > max_snapshot_lines + 40:
        keep_head = 30
        trimmed = lines[:keep_head] + ["… [快照过长已截断]"] + lines[-max_snapshot_lines:]
        user_prompt = "\n".join(trimmed)

    return _ask_judge(client, JUDGE_SYSTEM_PROMPT, user_prompt, phase="judge", mode="informed")


def _judge_blind(
    client: LLMClient, case: Case, exec_result: ExecutionResult, max_snapshot_lines: int
) -> dict:
    user_prompt = f"""# 功能
{case.title}

# expected
{chr(10).join(f"{i}. {e}" for i, e in enumerate(case.expected))}

# 最终页面文本快照（含行号）
{exec_result.final_snapshot_numbered or "(最终快照为空)"}

请按系统提示的三态规则输出 JSON 判定。"""
    lines = user_prompt.splitlines()
    if len(lines) > max_snapshot_lines + 20:
        user_prompt = "\n".join(lines[:12] + ["… [快照过长已截断]"] + lines[-max_snapshot_lines:])
    return _ask_judge(
        client, BLIND_JUDGE_SYSTEM_PROMPT, user_prompt, phase="judge:blind", mode="blind"
    )


def _ask_judge(client: LLMClient, system: str, user_prompt: str, *, phase: str, mode: str) -> dict:
    fallback = {
        "verdict": "unsure",
        "reason": "裁判输出不可解析，降级为 unsure（不允许默认 pass）",
        "evidence": [],
        "parsed": False,
        "mode": mode,
    }
    try:
        raw = client.chat_json(phase=phase, system=system, user=user_prompt)
    except Exception as exc:  # noqa: BLE001 —— 任何 LLM 故障都降级为 unsure
        fallback["reason"] = f"裁判调用失败: {exc}"
        return fallback

    verdict = raw.get("verdict")
    if verdict not in VALID_VERDICTS:
        fallback["reason"] = f"裁判输出 verdict 非法: {verdict!r}"
        return fallback
    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    cleaned_evidence = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        cleaned_evidence.append(
            {
                "expected_index": item.get("expected_index"),
                "snapshot_line": item.get("snapshot_line"),
                "quote": str(item.get("quote", ""))[:200],
            }
        )
    return {
        "verdict": verdict,
        "reason": str(raw.get("reason", ""))[:500],
        "evidence": cleaned_evidence,
        "parsed": True,
        "mode": mode,
    }


def assert_only_verdict(exec_result: ExecutionResult) -> dict:
    """消融口径：不用 LLM，结论只由步骤结果机械推导（有失败步骤 -> fail，否则 pass，无 unsure）。"""
    return {
        "verdict": "fail" if exec_result.failed_step else "pass",
        "reason": "ablation: no LLM judge, verdict derived from step results only",
        "evidence": [],
        "parsed": True,
        "mode": "assert_only",
    }
