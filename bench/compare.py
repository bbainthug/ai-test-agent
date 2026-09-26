"""B2：两次基准结果并排对比（基线 vs grounded）。

用法：uv run python -m bench.compare bench/results/20260925-full bench/results/<date>-grounded
输出并排表（覆盖、三种裁判的误报/漏报/一致率、成本），写 <B_DIR>/comparison.md。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .metrics import compute, to_markdown  # noqa: F401  (compute 供缺 summary 时重算)

JUDGE_NAMES = (
    ("informed", "LLM 裁判（看步骤结果）"),
    ("blind", "LLM 盲裁判（只看页面）"),
    ("assert_only", "纯断言（无 LLM）"),
)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "—"
    d = (b - a) * 100
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.1f}pp"


def load_summary(d: Path) -> tuple[dict, dict]:
    d = Path(d)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    sp = d / "summary.json"
    if sp.exists():
        return json.loads(sp.read_text(encoding="utf-8")), meta
    records = [json.loads(line) for line in (d / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return compute(records), meta


def _short(d: Path) -> str:
    p = Path(d)
    planner = ""
    meta_path = p / "meta.json"
    if meta_path.exists():
        planner = json.loads(meta_path.read_text(encoding="utf-8")).get("planner", "")
    name = p.name
    return f"{name} ({planner})" if planner else name


def build_comparison(dir_a: Path, dir_b: Path) -> str:
    a, meta_a = load_summary(dir_a)
    b, meta_b = load_summary(dir_b)
    lines = [
        f"# 基准对比：{_short(dir_a)} → {_short(dir_b)}",
        "",
        f"- A（基线）: `{dir_a}`，{meta_a.get('started_at')}，模型 {meta_a.get('model')}",
        f"- B: `{dir_b}`，{meta_b.get('started_at')}，模型 {meta_b.get('model')}",
        "",
        "## 总表",
        "",
        "| 指标 | A（基线） | B | 变化 |",
        "|---|---|---|---|",
    ]
    ma, mb = a, b

    def row(label, va, vb, fmt=str):
        lines.append(f"| {label} | {fmt(va)} | {fmt(vb)} | {fmt(vb - va) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else '—'} |")

    row("功能数", ma["features"], mb["features"])
    row("运行次数", ma["runs"], mb["runs"])
    row("planner 产出合法用例", _pct(ma["planner_valid_rate"]), _pct(mb["planner_valid_rate"]))
    lines.append(
        f"| 覆盖：至少一轮被覆盖的功能 | {ma['coverage']['features_covered_at_least_once']}/{ma['coverage']['features']} | "
        f"{mb['coverage']['features_covered_at_least_once']}/{mb['coverage']['features']} | "
        f"{mb['coverage']['features_covered_at_least_once'] - ma['coverage']['features_covered_at_least_once']:+d} |"
    )
    row("覆盖：按运行计", _pct(ma["coverage"]["run_coverage_rate"]), _pct(mb["coverage"]["run_coverage_rate"]),
        str)
    lines.append("")
    lines.append("| 裁判 | A 误报率（健康·已覆盖） | B 误报率 | 变化 | A 漏报率 | B 漏报率 | 变化 | A 一致率 | B 一致率 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for j, name in JUDGE_NAMES:
        ha, hb = ma["healthy"][j], mb["healthy"][j]
        fa, fb = ma["fault"][j], mb["fault"][j]
        ca, cb = ma["consistency"][j], mb["consistency"][j]
        lines.append(
            f"| {name} | {_pct(ha['false_alarm_rate'])}（{ha['covered_runs']}） | "
            f"{_pct(hb['false_alarm_rate'])}（{hb['covered_runs']}） | {_delta(ha['false_alarm_rate'], hb['false_alarm_rate'])} | "
            f"{_pct(fa['miss_rate'])}（{fa['fault_runs']}） | {_pct(fb['miss_rate'])}（{fb['fault_runs']}） | "
            f"{_delta(fa['miss_rate'], fb['miss_rate'])} | "
            f"{_pct(ca['rate'])} | {_pct(cb['rate'])} |"
        )
    ca, cb = ma["cost"], mb["cost"]
    lines += [
        "",
        "## 成本",
        "",
        "| 指标 | A（基线） | B | 变化 |",
        "|---|---|---|---|",
    ]
    lines.append(f"| tokens 总计 | {ca['total_tokens']:,} | {cb['total_tokens']:,} | {cb['total_tokens'] - ca['total_tokens']:+,} |")
    lines.append(f"| tokens / 运行 | {ca['tokens_per_run']:,} | {cb['tokens_per_run']:,} | {cb['tokens_per_run'] - ca['tokens_per_run']:+,} |")
    lines.append(f"| LLM 调用耗时累计 (s) | {ca['llm_seconds_total']} | {cb['llm_seconds_total']} | {cb['llm_seconds_total'] - ca['llm_seconds_total']:+} |")
    lines.append(f"| 总墙钟 (s，按轮最大并发折算) | {ca['wall_seconds_total']} | {cb['wall_seconds_total']} | {cb['wall_seconds_total'] - ca['wall_seconds_total']:+} |")
    lines.append(f"| 失败 LLM 调用 | {ca['llm_calls_failed']} | {cb['llm_calls_failed']} | {cb['llm_calls_failed'] - ca['llm_calls_failed']:+d} |")
    explore_b = _explore_seconds(dir_b)
    lines.append(f"| 探索墙钟 (s，grounded 专属) | — | {explore_b:.1f} | — |")
    lines += [
        "",
        "## 逐功能对比（覆盖率 = 覆盖轮数 / 合法用例轮数；informed 结论为健康系统各轮）",
        "",
        "| 功能 | A 覆盖 | B 覆盖 | Δ | A informed | B informed |",
        "|---|---|---|---|---|---|",
    ]
    pf_a, pf_b = ma["per_feature"], mb["per_feature"]
    for fid in sorted(set(pf_a) | set(pf_b)):
        pa, pb = pf_a.get(fid), pf_b.get(fid)
        ca_n = pa["covered"] if pa else 0
        cb_n = pb["covered"] if pb else 0
        va = " ".join(pa["informed"]) if pa else "—"
        vb = " ".join(pb["informed"]) if pb else "—"
        mark = "→" if cb_n > ca_n else ("↓" if cb_n < ca_n else "=")
        lines.append(f"| {fid} | {ca_n} | {cb_n} | {mark} | {va} | {vb} |")
    return "\n".join(lines) + "\n"


def _explore_seconds(d: Path) -> float:
    total = 0.0
    p = Path(d) / "runs.jsonl"
    if not p.exists():
        return 0.0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        g = json.loads(line).get("grounding") or {}
        total += g.get("explore_seconds") or 0.0
    return total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bench.compare")
    ap.add_argument("dir_a", help="基线结果目录")
    ap.add_argument("dir_b", help="对比结果目录")
    args = ap.parse_args(argv)
    md = build_comparison(Path(args.dir_a), Path(args.dir_b))
    out = Path(args.dir_b) / "comparison.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
