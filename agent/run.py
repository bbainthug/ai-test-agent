"""端到端入口：一条用例 -> 执行 -> 裁判 -> 报告。

用法：
  python -m agent.run --case cases/01_login.json
  python -m agent.run --case cases/02_create_publish_post.json --skip-judge   # 纯断言消融
产出：
  runs/<run_id>/        步骤截图、calls.jsonl（LLM 审计）
  reports/<run_id>.json / .md
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .config import ConfigError, Settings, load_settings
from .executor import Executor
from .judge import JUDGE_MODES, assert_only_verdict, judge_execution
from .llm import LLMClient
from .report import build_report, write_report
from .schema import Case


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")[:40]


def make_run_id(case: Case) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{_slug(case.id)}"


def run_case_file(
    case_path: Path,
    settings: Settings,
    *,
    skip_judge: bool = False,
    judge_mode: str = "informed",
    reports_dir: Path = Path("reports"),
    runs_dir: Path = Path("runs"),
) -> dict:
    raw = json.loads(case_path.read_text(encoding="utf-8"))
    case = Case.model_validate(raw)

    run_id = make_run_id(case)
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    exec_result = Executor(settings, run_dir).run_case(case)

    judge_result = None
    if not skip_judge:
        settings.require_llm_config()
        client = LLMClient(
            run_id=run_id,
            run_dir=run_dir,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout_s=settings.llm_timeout_s,
        )
        judge_result = judge_execution(client, case, exec_result, mode=judge_mode)
    else:
        # 消融口径：纯断言，无 LLM 裁判
        judge_result = assert_only_verdict(exec_result)

    report = build_report(
        run_id=run_id,
        case=case,
        exec_result=exec_result,
        judge_result=judge_result,
        run_dir=run_dir,
        halo_image=settings.halo_image,
        llm_model=settings.llm_model if not skip_judge else "none",
    )
    write_report(report, reports_dir)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent.run", description=__doc__)
    parser.add_argument("--case", required=True, help="用例 JSON 路径")
    parser.add_argument("--skip-judge", action="store_true", help="关闭 LLM 裁判（纯断言消融口径）")
    parser.add_argument(
        "--judge-mode", choices=JUDGE_MODES, default="informed",
        help="informed=裁判能看到步骤结果（默认）；blind=只看 expected 与最终快照",
    )
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--runs-dir", default="runs")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[config] {exc}")
        return 2

    report = run_case_file(
        Path(args.case),
        settings,
        skip_judge=args.skip_judge,
        judge_mode=args.judge_mode,
        reports_dir=Path(args.reports_dir),
        runs_dir=Path(args.runs_dir),
    )
    ss = report["step_summary"]
    judge = report["judge"] or {}
    print(
        f"[run] {report['run_id']} steps={ss['passed']}P/{ss['failed']}F/{ss['skipped']}S "
        f"verdict={judge.get('verdict')} failure_classes={json.dumps(ss['failure_classes'], ensure_ascii=False)}"
    )
    print(f"[run] 报告: {report['artifacts'].get('report_json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
