"""验证人工基准：每条参考用例在健康系统上必须全部通过，注入故障后必须失败且故障被触发。

用法：uv run python -m bench.validate_reference [--only id1,id2]
输出：bench/reference_validation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from agent.config import load_settings

from .common import BENCH_DIR, execute, load_features, step_counts, writes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    only = {x for x in args.only.split(",") if x}
    settings = load_settings()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = Path("runs") / f"{stamp}-refval"
    out_path = BENCH_DIR / "reference_validation.json"
    results = json.loads(out_path.read_text()) if out_path.exists() and only else {}
    for f in load_features():
        if only and f.id not in only:
            continue
        healthy = execute(settings, f.reference, root / f.id / "healthy")
        row = {
            "healthy_steps": step_counts(healthy),
            "healthy_ok": healthy.failed_step is None,
            "healthy_writes": writes(healthy),
            "healthy_failed_at": (healthy.failed_step.index, healthy.failed_step.failure_class,
                                  (healthy.failed_step.error or "")[:160]) if healthy.failed_step else None,
        }
        if "__FILL" in f.fault.url_regex:
            row["fault"] = "pending: fill regex from healthy_writes"
        else:
            faulted = execute(settings, f.reference, root / f.id / "fault", faults=[f.fault])
            row.update({
                "fault_steps": step_counts(faulted),
                "fault_hit": faulted.faults_hit,
                "fault_detected": faulted.failed_step is not None and faulted.faults_hit > 0,
                "fault_failed_at": (faulted.failed_step.index, faulted.failed_step.failure_class)
                if faulted.failed_step else None,
            })
            if not row["fault_detected"]:
                row["fault_final_snapshot_tail"] = faulted.final_snapshot_numbered[-1500:]
        row["valid"] = row["healthy_ok"] and row.get("fault_detected", False)
        results[f.id] = row
        print(f"{f.id:18} healthy={'OK ' if row['healthy_ok'] else 'BAD'} "
              f"fault={row.get('fault_detected', row.get('fault'))} hit={row.get('fault_hit')}", flush=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results.values() if r["valid"])
    print(f"valid {ok}/{len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
