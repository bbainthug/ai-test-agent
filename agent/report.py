"""报告生成：reports/<run_id>.json + 同名 Markdown。

原则（任务包 §0「先做再写」）：
- 报告只记录真实发生的事：步骤结果、裁判结论、LLM 成本、产物路径；
- README 里出现的每个数字都必须能从这些 JSON 复现；
- 敏感值（管理员密码）在进入报告前已由 executor/snapshot 层脱敏，
  步骤参数保留用例里的占位符原文。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .executor import ExecutionResult
from .llm import summarize_calls
from .schema import Case


def build_report(
    *,
    run_id: str,
    case: Case,
    exec_result: ExecutionResult,
    judge_result: dict | None,
    run_dir: Path,
    halo_image: str,
    llm_model: str,
) -> dict:
    steps = exec_result.to_dict()["steps"]
    failure_classes: dict[str, int] = {}
    for s in exec_result.steps:
        if s.status == "failed" and s.failure_class:
            failure_classes[s.failure_class] = failure_classes.get(s.failure_class, 0) + 1

    llm_summary = summarize_calls(Path(run_dir) / "calls.jsonl")

    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": {
            "app": "halo",
            "version": halo_image,
            "base_url": "http://localhost:8090",
        },
        "llm": {"model": llm_model, **llm_summary},
        "case": case.model_dump(),
        "execution": exec_result.to_dict(),
        "step_summary": {
            "total": len(exec_result.steps),
            "passed": sum(1 for s in exec_result.steps if s.status == "passed"),
            "failed": sum(1 for s in exec_result.steps if s.status == "failed"),
            "skipped": sum(1 for s in exec_result.steps if s.status == "skipped"),
            "failure_classes": failure_classes,
        },
        "judge": judge_result,
        "artifacts": {
            "run_dir": str(run_dir),
            "calls_jsonl": str(Path(run_dir) / "calls.jsonl"),
        },
    }


def write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{report['run_id']}.json"
    md_path = out_dir / f"{report['run_id']}.md"
    report["artifacts"]["report_json"] = str(json_path)
    report["artifacts"]["report_md"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_markdown(report: dict) -> str:
    case = report["case"]
    ex = report["execution"]
    ss = report["step_summary"]
    judge = report.get("judge") or {}
    llm = report.get("llm", {})

    lines: list[str] = []
    lines.append(f"# Run {report['run_id']}")
    lines.append("")
    lines.append(f"- 用例: `{case['id']}` {case['title']}（优先级 {case['priority']}）")
    lines.append(f"- 时间: {ex['started_at']} -> {ex['finished_at']}（UTC）")
    lines.append(f"- 靶子: {report['target']['app']} {report['target']['version']} @ {report['target']['base_url']}")
    lines.append(f"- 步骤: {ss['passed']} passed / {ss['failed']} failed / {ss['skipped']} skipped")
    if ss["failure_classes"]:
        lines.append(f"- 失败分类: {json.dumps(ss['failure_classes'], ensure_ascii=False)}")
    lines.append(f"- 裁判: **{judge.get('verdict', 'N/A')}** — {judge.get('reason', '')}")
    lines.append(f"- LLM 成本: {llm.get('total_tokens', 0)} tokens / {llm.get('latency_ms', 0)} ms"
                 f"（{llm.get('calls_total', 0)} 次调用, 失败 {llm.get('calls_failed', 0)}）")
    lines.append("")

    lines.append("## 步骤")
    lines.append("")
    lines.append("| # | 动作 | 参数 | 状态 | 失败分类 | 耗时ms |")
    lines.append("|---|------|------|------|----------|--------|")
    for s in ex["steps"]:
        params = json.dumps(s["params"], ensure_ascii=False)
        lines.append(
            f"| {s['index']} | {s['action']} | `{params}` | {s['status']} "
            f"| {s.get('failure_class') or '-'} | {s['elapsed_ms']} |"
        )
    lines.append("")

    if ex.get("final_snapshot_numbered"):
        lines.append("## 最终快照（节选，前 60 行）")
        lines.append("")
        lines.append("```")
        lines.extend(ex["final_snapshot_numbered"].splitlines()[:60])
        lines.append("```")
        lines.append("")

    if judge.get("evidence"):
        lines.append("## 裁判证据")
        lines.append("")
        for ev in judge["evidence"]:
            lines.append(f"- L{ev.get('snapshot_line')}: `{ev.get('quote')}`（expected_index={ev.get('expected_index')}）")
        lines.append("")
    return "\n".join(lines)
