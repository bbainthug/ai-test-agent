import pytest
from conftest import FakeLLM

from agent.executor import ExecutionResult, StepResult
from agent.judge import assert_only_verdict, judge_execution
from agent.schema import Case

CASE = Case.model_validate({
    "id": "c1", "title": "改站点标题", "priority": "P1",
    "steps": [{"action": "goto", "url": "/"}],
    "expected": ["页面显示新标题"],
})


def _exec(failed=False):
    r = ExecutionResult(case_id="c1", started_at="", finished_at="", final_url="/")
    r.steps = [StepResult(1, "goto", {"url": "/"}, "failed" if failed else "passed",
                          failure_class="timeout" if failed else None)]
    r.final_snapshot_numbered = "L1: - heading \"新标题\""
    return r


def test_valid_verdict_and_evidence_cleaned():
    llm = FakeLLM([{"verdict": "pass", "reason": "ok", "evidence": [
        {"expected_index": 0, "snapshot_line": 1, "quote": "x" * 500}, "garbage"]}])
    out = judge_execution(llm, CASE, _exec())
    assert out["verdict"] == "pass" and out["parsed"] and out["mode"] == "informed"
    assert len(out["evidence"]) == 1 and len(out["evidence"][0]["quote"]) == 200


@pytest.mark.parametrize("bad", [{"verdict": "maybe"}, {"verdict": None}, {}])
def test_invalid_verdict_degrades_to_unsure(bad):
    out = judge_execution(FakeLLM([bad]), CASE, _exec())
    assert out["verdict"] == "unsure" and out["parsed"] is False


def test_llm_error_degrades_to_unsure_never_pass():
    out = judge_execution(FakeLLM(raise_with=RuntimeError("boom")), CASE, _exec())
    assert out["verdict"] == "unsure" and "boom" in out["reason"]


def test_informed_prompt_includes_step_results():
    llm = FakeLLM([{"verdict": "pass", "reason": "", "evidence": []}])
    judge_execution(llm, CASE, _exec())
    assert "执行步骤结果" in llm.calls[0]["user"] and "-> passed" in llm.calls[0]["user"]


def test_blind_prompt_hides_step_results():
    llm = FakeLLM([{"verdict": "unsure", "reason": "", "evidence": []}])
    out = judge_execution(llm, CASE, _exec(failed=True), mode="blind")
    user = llm.calls[0]["user"]
    assert out["mode"] == "blind" and llm.calls[0]["phase"] == "judge:blind"
    assert "passed" not in user and "failed" not in user and "失败分类" not in user
    assert "新标题" in user  # 最终快照仍在


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        judge_execution(FakeLLM(), CASE, _exec(), mode="psychic")


def test_assert_only_verdict():
    assert assert_only_verdict(_exec())["verdict"] == "pass"
    assert assert_only_verdict(_exec(failed=True))["verdict"] == "fail"
