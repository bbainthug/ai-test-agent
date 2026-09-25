from bench.metrics import compute, to_markdown


def _rec(rnd, fid, planner="ok", probe=1, verdicts=("pass", "pass", "pass"), fault=None, tokens=100):
    r = {"round": rnd, "feature": fid, "priority": "P1", "planner": planner, "seconds": 10,
         "llm": {"total_tokens": tokens, "latency_ms": 1000, "calls_failed": 0,
                 "by_phase": {"plan:r1": {"calls": 1, "total_tokens": 40, "latency_ms": 1},
                              "judge": {"calls": 1, "total_tokens": 30, "latency_ms": 1}}}}
    if planner == "ok":
        r["healthy"] = {"probe_hits": probe, "faults_hit": 0,
                        "judges": dict(zip(("informed", "blind", "assert_only"),
                                           ({"verdict": v} for v in verdicts)))}
    if fault:
        hit, vs = fault
        r["fault"] = {"faults_hit": hit, "probe_hits": 0,
                      "judges": dict(zip(("informed", "blind", "assert_only"), ({"verdict": v} for v in vs)))}
    return r


def test_rates_follow_documented_definitions():
    recs = [
        _rec(1, "a", fault=(1, ("fail", "pass", "fail"))),
        _rec(2, "a"),
        _rec(1, "b", verdicts=("unsure", "fail", "pass"), fault=(1, ("pass", "pass", "pass"))),
        _rec(2, "b", verdicts=("pass", "pass", "pass")),
        _rec(1, "c", probe=0, fault=(0, ("pass", "pass", "pass"))),  # 未覆盖、故障未触发
        _rec(2, "c", planner="failed"),
    ]
    m = compute(recs)
    assert m["planner_valid_rate"] == round(5 / 6, 4)
    assert m["coverage"]["features_covered_at_least_once"] == 2
    # 已覆盖的健康运行 4 次，informed 非 pass 1 次
    assert m["healthy"]["informed"]["false_alarm_rate"] == 0.25
    assert m["healthy"]["informed"]["unsure"] == 1
    # 故障被触发的 2 次：informed 放过 1 次；blind 放过 2 次
    assert m["fault"]["informed"]["miss_rate"] == 0.5
    assert m["fault"]["blind"]["miss_rate"] == 1.0
    # 一致性：a 两轮都 pass（稳定），b 一轮 unsure 一轮 pass（不稳定），c 有一轮没产出用例不计
    assert m["consistency"]["informed"] == {"stable_features": 1, "features": 2, "rate": 0.5}
    assert m["cost"]["total_tokens"] == 600
    assert "误报率" in to_markdown(m, {"rounds": 2})
