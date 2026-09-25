import json

import pytest
from conftest import FakeLLM

from agent.executor import ExecutionResult, StepResult
from agent.llm import extract_json, summarize_calls
from agent.planner import PlannerError, plan_case
from agent.report import build_report
from agent.schema import Case

GOOD = {
    "id": "view-users", "feature_id": "users", "title": "查看用户", "priority": "P1",
    "steps": [{"action": "goto", "url": "http://localhost:8090/console/users"}],
    "expected": ["用户列表可见"],
}


def test_planner_repairs_once_with_validation_error():
    bad = dict(GOOD, steps=[{"action": "click"}])
    llm = FakeLLM([bad, GOOD])
    case = plan_case(llm, feature_desc="看用户", feature_id="users")
    assert case.id == "view-users"
    assert len(llm.calls) == 2 and "未通过 schema 校验" in llm.calls[1]["user"]


def test_planner_gives_up_after_max_rounds():
    bad = dict(GOOD, steps=[])
    with pytest.raises(PlannerError):
        plan_case(FakeLLM([bad, bad]), feature_desc="x", feature_id="x")


@pytest.mark.parametrize(
    "text",
    ['{"a": 1}', '```json\n{"a": 1}\n```', 'sure! {"a": 1} hope this helps'],
)
def test_extract_json_tolerates_wrappers(text):
    assert extract_json(text) == {"a": 1}


def test_extract_json_rejects_non_json():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_summarize_calls(tmp_path):
    p = tmp_path / "calls.jsonl"
    rows = [
        {"phase": "plan:r1", "ok": True, "total_tokens": 100, "prompt_tokens": 80,
         "completion_tokens": 20, "latency_ms": 5},
        {"phase": "judge", "ok": False, "latency_ms": 7},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    s = summarize_calls(p)
    assert s["calls_total"] == 2 and s["calls_failed"] == 1
    assert s["total_tokens"] == 100 and s["latency_ms"] == 12
    assert s["by_phase"]["judge"]["calls"] == 1
    assert summarize_calls(tmp_path / "missing.jsonl")["calls_total"] == 0


def test_build_report_step_summary(tmp_path):
    case = Case.model_validate(GOOD)
    r = ExecutionResult(case_id="view-users", started_at="", finished_at="", final_url="")
    r.steps = [
        StepResult(1, "goto", {}, "passed"),
        StepResult(2, "click", {}, "failed", failure_class="locator_failed"),
        StepResult(3, "assert_text", {}, "skipped"),
    ]
    rep = build_report(run_id="r", case=case, exec_result=r, judge_result=None,
                       run_dir=tmp_path, halo_image="img", llm_model="m")
    assert rep["step_summary"] == {
        "total": 3, "passed": 1, "failed": 1, "skipped": 1,
        "failure_classes": {"locator_failed": 1},
    }
