"""基准测试公共部分：加载功能清单、执行一条用例（可注入故障）、汇总步骤结果。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from agent.executor import ExecutionResult, Executor, Fault
from agent.schema import Case

BENCH_DIR = Path(__file__).resolve().parent
FEATURES_PATH = BENCH_DIR / "features.json"


@dataclass(frozen=True)
class Feature:
    id: str
    title: str
    description: str
    priority: str
    fault: Fault
    reference: Case


def load_features(path: Path = FEATURES_PATH) -> list[Feature]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for f in data["features"]:
        fault = Fault(url_regex=f["fault"]["url_regex"], status=f["fault"].get("status", 500),
                      method=f["fault"].get("method"))
        out.append(Feature(f["id"], f["title"], f["description"], f["priority"], fault,
                           Case.model_validate(f["reference"])))
    return out


# Halo 2.20 默认登录限流：每个 IP 每分钟 3 次（resilience4j.ratelimiter.configs.authentication）。
# 不改被测系统配置，而是让基准自己节流：含登录的运行之间至少间隔 LOGIN_GAP_S 秒。
LOGIN_GAP_S = 21.0
_last_login_at = 0.0


def _needs_login(case: Case) -> bool:
    return any(s.action == "goto" and s.url and s.url.rstrip("/").endswith("/login") for s in case.steps)


def execute(
    settings, case: Case, run_dir: Path, faults: list[Fault] | None = None,
    probes: list[Fault] | None = None,
) -> ExecutionResult:
    global _last_login_at
    if _needs_login(case):
        wait = LOGIN_GAP_S - (time.monotonic() - _last_login_at)
        if wait > 0:
            time.sleep(wait)
        _last_login_at = time.monotonic()
    return Executor(settings, run_dir, faults=faults, probes=probes).run_case(case)


def step_counts(r: ExecutionResult) -> dict:
    st = [s.status for s in r.steps]
    return {k: st.count(k) for k in ("passed", "failed", "skipped")}


def writes(r: ExecutionResult) -> list[str]:
    return sorted(k for k in r.api_calls if not k.startswith("GET "))
