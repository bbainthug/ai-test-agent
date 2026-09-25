"""阶段 B 基准：planner → executor → 三种裁判，20 个功能 × N 轮，第 1 轮额外做故障注入。

每个 (轮次, 功能)：
1. planner 由一句话功能描述生成用例（新调用，不复用上一轮）；
2. 健康系统上执行，探针统计是否请求到了该功能的关键接口（= 是否覆盖）；
3. 三种裁判：informed（看得到步骤结果）、blind（只看 expected + 最终页面）、assert_only（不用 LLM）；
4. 仅第 1 轮：同一条用例在注入该功能故障后再执行一次，三种裁判再判一次（漏报率）。

用法：uv run python -m bench.run_bench [--rounds 5] [--only f1,f2] [--out-dir bench/results/<ts>]
每条记录追加写入 <out-dir>/runs.jsonl（中断后可 --resume 续跑）；汇总见 bench.metrics。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from agent.config import load_settings
from agent.judge import assert_only_verdict, judge_execution
from agent.llm import LLMClient, LLMError, summarize_calls
from agent.planner import PlannerError, plan_case

from .common import BENCH_DIR, execute, load_features, step_counts


def _client(settings, run_dir: Path) -> LLMClient:
    return LLMClient(
        run_id=run_dir.name, run_dir=run_dir, base_url=settings.llm_base_url,
        api_key=settings.llm_api_key, model=settings.llm_model,
        temperature=settings.llm_temperature, timeout_s=settings.llm_timeout_s,
    )


def _judge_once_retry(client, case, result, mode: str) -> dict:
    """调用失败（超时、网关错误）重试一次：网络故障不是裁判的判断，不应算进指标。
    两次都失败才保留降级的 unsure，并标记 call_error 以便单独统计。"""
    j = judge_execution(client, case, result, mode=mode)
    if not j["parsed"] and j["reason"].startswith("裁判调用失败"):
        j = judge_execution(client, case, result, mode=mode)
    return {"verdict": j["verdict"], "parsed": j["parsed"], "reason": j["reason"][:300],
            "call_error": not j["parsed"] and j["reason"].startswith("裁判调用失败")}


def _judges(pool: ThreadPoolExecutor, client, case, result) -> dict:
    futs = {m: pool.submit(_judge_once_retry, client, case, result, m) for m in ("informed", "blind")}
    out = {m: f.result() for m, f in futs.items()}
    out["assert_only"] = {"verdict": assert_only_verdict(result)["verdict"], "parsed": True,
                          "reason": "", "call_error": False}
    return out


def _exec_summary(r) -> dict:
    return {
        "steps": step_counts(r),
        "failed_at": (r.failed_step.index, r.failed_step.failure_class) if r.failed_step else None,
        "probe_hits": r.probe_hits,
        "faults_hit": r.faults_hit,
        "final_url": r.final_url,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--only", default="")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--resume", action="store_true", help="跳过 runs.jsonl 里已有的 (round, feature)")
    ap.add_argument("--workers", type=int, default=6, help="并发的 LLM 调用数（planner 与裁判）")
    args = ap.parse_args(argv)
    settings = load_settings()
    settings.require_llm_config()
    only = {x for x in args.only.split(",") if x}
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else BENCH_DIR / "results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path = out_dir / "runs.jsonl"
    done = set()
    if args.resume and runs_path.exists():
        for line in runs_path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            done.add((rec["round"], rec["feature"]))
    features = [f for f in load_features() if not only or f.id in only]
    (out_dir / "meta.json").write_text(json.dumps({
        "started_at": stamp, "rounds": args.rounds, "features": [f.id for f in features],
        "model": settings.llm_model, "halo_image": settings.halo_image,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    pool = ThreadPoolExecutor(max_workers=args.workers)
    judge_pool = ThreadPoolExecutor(max_workers=args.workers)  # 与外层分开，避免嵌套提交死锁
    for rnd in range(1, args.rounds + 1):
        todo = [f for f in features if (rnd, f.id) not in done]
        if not todo:
            continue
        # 1) 本轮全部功能并发生成用例（LLM 是瓶颈）
        ctx = {}
        for f in todo:
            run_dir = Path("runs") / f"{stamp}-bench" / f"r{rnd}" / f.id
            run_dir.mkdir(parents=True, exist_ok=True)
            client = _client(settings, run_dir)
            ctx[f.id] = (run_dir, client, time.time(),
                         pool.submit(plan_case, client, feature_desc=f.description, feature_id=f.id))
        # 2) 按顺序执行（受 Halo 登录限流约束），每条执行完就把裁判丢进线程池
        pending = []
        for f in todo:
            run_dir, client, t0, fut = ctx[f.id]
            rec = {"round": rnd, "feature": f.id, "priority": f.priority}
            try:
                case = fut.result()
                rec["planner"] = "ok"
                rec["case"] = case.model_dump()
            except (PlannerError, LLMError) as exc:
                rec["planner"] = "failed"
                rec["planner_error"] = str(exc)[:300]
                case = None
            jobs = {}
            if case is not None:
                healthy = execute(settings, case, run_dir / "healthy", probes=[f.fault])
                rec["healthy"] = _exec_summary(healthy)
                jobs["healthy"] = pool.submit(_judges, judge_pool, client, case, healthy)
                if rnd == 1:
                    faulted = execute(settings, case, run_dir / "fault", faults=[f.fault])
                    rec["fault"] = _exec_summary(faulted)
                    jobs["fault"] = pool.submit(_judges, judge_pool, client, case, faulted)
            pending.append((f, rec, run_dir, t0, jobs))
        # 3) 收齐裁判结果、落盘
        for f, rec, run_dir, t0, jobs in pending:
            for key, j in jobs.items():
                rec[key]["judges"] = j.result()
            rec["llm"] = summarize_calls(run_dir / "calls.jsonl")
            rec["seconds"] = round(time.time() - t0, 1)
            with runs_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            h = rec.get("healthy", {})
            print(f"r{rnd} {f.id:18} planner={rec['planner']:6} "
                  f"covered={bool(h.get('probe_hits'))!s:5} steps={h.get('steps')} "
                  f"verdicts={ {k: v['verdict'] for k, v in h.get('judges', {}).items()} } "
                  f"{'fault_hit=' + str(rec['fault']['faults_hit']) if 'fault' in rec else ''}", flush=True)
    pool.shutdown()
    judge_pool.shutdown()
    print(f"done -> {runs_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
