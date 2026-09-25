"""由 runs.jsonl 计算阶段 B 指标，写 summary.json / summary.md。

口径（与 README 一致）：
- 覆盖：planner 产出合法用例，且健康执行时请求到了该功能的关键接口（探针命中）。
- 误报率：健康系统上、已覆盖的运行中，裁判给出非 pass 的比例（fail 与 unsure 分开列）。
- 漏报率：第 1 轮注入故障、且故障确实被触发的运行中，裁判仍给出 pass 的比例。
- 一致率：同一功能 N 轮 informed 裁判结论完全相同的功能占比（只统计 N 轮都产出用例的功能）。
- 成本：planner + 两种 LLM 裁判的 token 与耗时。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

JUDGES = ("informed", "blind", "assert_only")


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _wall_seconds(records: list[dict]) -> float:
    per_round: dict[int, float] = defaultdict(float)
    for r in records:
        per_round[r["round"]] = max(per_round[r["round"]], r.get("seconds", 0))
    return round(sum(per_round.values()), 1)


def compute(records: list[dict]) -> dict:
    by_feature: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_feature[r["feature"]].append(r)
    features = sorted(by_feature)
    runs = len(records)
    planned = [r for r in records if r.get("planner") == "ok"]
    covered = [r for r in planned if r["healthy"]["probe_hits"] > 0]

    healthy_stats = {}
    for j in JUDGES:
        v = [r["healthy"]["judges"][j]["verdict"] for r in covered]
        v_all = [r["healthy"]["judges"][j]["verdict"] for r in planned]
        healthy_stats[j] = {
            "covered_runs": len(v),
            "false_alarm_rate": _rate(sum(x != "pass" for x in v), len(v)),
            "fail": v.count("fail"), "unsure": v.count("unsure"), "pass": v.count("pass"),
            "false_alarm_rate_all_planned": _rate(sum(x != "pass" for x in v_all), len(v_all)),
        }

    faulted = [r for r in records if "fault" in r]
    fault_hit = [r for r in faulted if r["fault"]["faults_hit"] > 0]
    fault_stats = {}
    for j in JUDGES:
        v = [r["fault"]["judges"][j]["verdict"] for r in fault_hit]
        fault_stats[j] = {
            "fault_runs": len(v),
            "miss_rate": _rate(v.count("pass"), len(v)),
            "fail": v.count("fail"), "unsure": v.count("unsure"), "pass": v.count("pass"),
        }

    consistency = {}
    for j in JUDGES:
        stable = total = 0
        for rs in by_feature.values():
            vs = [r["healthy"]["judges"][j]["verdict"] for r in rs if r.get("planner") == "ok"]
            if len(vs) == len(rs) and len(vs) > 1:
                total += 1
                stable += len(set(vs)) == 1
        consistency[j] = {"stable_features": stable, "features": total, "rate": _rate(stable, total)}

    def _fault_row(rs: list[dict]) -> dict | None:
        fr = [r for r in rs if "fault" in r]
        if not fr:
            return None
        return {"hit": fr[0]["fault"]["faults_hit"] > 0,
                **{j: fr[0]["fault"]["judges"][j]["verdict"] for j in JUDGES}}

    per_feature = {}
    for fid, rs in sorted(by_feature.items()):
        ok = [r for r in rs if r.get("planner") == "ok"]
        per_feature[fid] = {
            "rounds": len(rs),
            "planned": len(ok),
            "covered": sum(r["healthy"]["probe_hits"] > 0 for r in ok),
            "informed": [r["healthy"]["judges"]["informed"]["verdict"] if r.get("planner") == "ok" else "-"
                         for r in sorted(rs, key=lambda x: x["round"])],
            "fault": _fault_row(rs),
        }

    tokens = sum(r["llm"]["total_tokens"] for r in records)
    latency = sum(r["llm"]["latency_ms"] for r in records)
    phases: dict[str, dict] = defaultdict(lambda: {"calls": 0, "total_tokens": 0})
    for r in records:
        for ph, b in r["llm"]["by_phase"].items():
            key = "plan" if ph.startswith("plan") else ph
            phases[key]["calls"] += b["calls"]
            phases[key]["total_tokens"] += b["total_tokens"]
    return {
        "runs": runs,
        "features": len(features),
        "planner_valid_rate": _rate(len(planned), runs),
        "coverage": {
            "features_covered_at_least_once": sum(1 for f in per_feature.values() if f["covered"]),
            "features": len(features),
            "run_coverage_rate": _rate(len(covered), runs),
        },
        "healthy": healthy_stats,
        "fault": fault_stats,
        "consistency": consistency,
        "cost": {
            "total_tokens": tokens,
            "tokens_per_run": round(tokens / runs) if runs else None,
            "llm_seconds_total": round(latency / 1000, 1),
            # seconds 是"本轮开始 → 该记录落盘"的累计值，同轮记录共享起点：每轮取最大值再求和
            "wall_seconds_total": _wall_seconds(records),
            "by_phase": dict(phases),
            "llm_calls_failed": sum(r["llm"]["calls_failed"] for r in records),
        },
        "per_feature": per_feature,
    }


def to_markdown(m: dict, meta: dict) -> str:
    pct = lambda x: "—" if x is None else f"{x * 100:.1f}%"
    lines = [
        f"# 阶段 B 基准结果（{meta.get('started_at', '')}，模型 {meta.get('model', '')}）",
        "",
        (f"- 功能 {m['features']} 个 × {meta.get('rounds')} 轮 = {m['runs']} 次运行；"
         f"planner 产出合法用例 {pct(m['planner_valid_rate'])}"),
        (f"- 覆盖：{m['coverage']['features_covered_at_least_once']}/{m['features']} 个功能至少一轮被覆盖；"
         f"按运行计 {pct(m['coverage']['run_coverage_rate'])}"),
        "",
        "| 裁判 | 误报率（健康·已覆盖） | fail / unsure | 漏报率（注入故障） | 一致率（N 轮结论相同） |",
        "|---|---|---|---|---|",
    ]
    for j, name in (("informed", "LLM 裁判（看步骤结果）"), ("blind", "LLM 盲裁判（只看页面）"),
                    ("assert_only", "纯断言（无 LLM）")):
        h, f, c = m["healthy"][j], m["fault"][j], m["consistency"][j]
        lines.append(
            f"| {name} | {pct(h['false_alarm_rate'])}（{h['covered_runs']} 次） | {h['fail']} / {h['unsure']} | "
            f"{pct(f['miss_rate'])}（{f['fault_runs']} 次） | {pct(c['rate'])}（{c['stable_features']}/{c['features']}） |"
        )
    cost = m["cost"]
    lines += [
        "",
        (f"成本：共 {cost['total_tokens']:,} tokens，平均每次运行 {cost['tokens_per_run']:,}；"
         f"LLM 调用耗时累计 {cost['llm_seconds_total']} s（并发，非墙钟），总墙钟 {cost['wall_seconds_total']} s；"
         f"失败调用 {cost['llm_calls_failed']} 次。"),
        "",
        "| 功能 | 合法用例 | 覆盖 | informed 各轮 | 故障注入（informed / blind / 断言） |",
        "|---|---|---|---|---|",
    ]
    for fid, pf in m["per_feature"].items():
        fz = pf["fault"]
        fs = "—" if not fz else (f"{fz['informed']} / {fz['blind']} / {fz['assert_only']}"
                                  + ("" if fz["hit"] else "（未触发）"))
        lines.append(f"| {fid} | {pf['planned']}/{pf['rounds']} | {pf['covered']}/{pf['rounds']} | "
                     f"{' '.join(pf['informed'])} | {fs} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    args = ap.parse_args(argv)
    d = Path(args.results_dir)
    records = [json.loads(line) for line in (d / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line]
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    m = compute(records)
    (d / "summary.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "summary.md").write_text(to_markdown(m, meta), encoding="utf-8")
    print(to_markdown(m, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
