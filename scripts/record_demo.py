"""录制 docs/media/demo.gif 的原始素材：一句话功能描述 -> planner 生成用例 ->
浏览器执行 -> 裁判结论 -> 报告；再故障注入重跑一次看裁判判 fail。

不改 agent/ 的任何逻辑——只按公开 API 组合调用 planner/executor/judge/report
（与 agent/run.py、bench/run_bench.py 的调用方式相同），录像通过给
playwright.sync_api.Browser.new_context 打补丁临时注入 record_video_dir 实现，
补丁只在本脚本进程内、Executor.run_case 期间生效，用完即还原，不写回任何库文件。

用法（需要 Halo 已通过 ./scripts/up.sh 起好、.env 配好 LLM_API_KEY）：
  uv run python scripts/record_demo.py
输出：
  runs/_demo_video/*.webm   两段原始录像（健康 / 故障注入）
  reports/<run_id>.*        两条真实报告（与仓库其余报告同一套产出路径）
再用 ffmpeg 从 .webm 剪成 docs/media/demo.gif（命令见 README「演示 GIF」一节）。
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import playwright.sync_api as pw

from agent.config import load_settings
from agent.executor import Executor, Fault
from agent.explorer import Explorer
from agent.judge import judge_execution
from agent.llm import LLMClient
from agent.planner import plan_case
from agent.report import build_report, write_report
from agent.run import make_run_id

VIDEO_DIR = Path("runs/_demo_video")
FEATURE_DESC = "登录后在系统设置里修改站点标题并保存，前台首页显示新标题"
FEATURE_ID = "site-title"
# 与 bench/features.json 里 site-title 的故障定义一致
FAULT = Fault(url_regex=r"/api/v1alpha1/configmaps/system", status=500, method="PUT")


@contextlib.contextmanager
def _video_recording():
    """临时给 Browser.new_context 打补丁注入录像目录；退出时还原。"""
    orig = pw.Browser.new_context

    def patched(self, **kwargs):
        kwargs.setdefault("record_video_dir", str(VIDEO_DIR))
        kwargs.setdefault("record_video_size", {"width": 1440, "height": 900})
        return orig(self, **kwargs)

    pw.Browser.new_context = patched
    try:
        yield
    finally:
        pw.Browser.new_context = orig


def _run_and_report(settings, client, case, *, faults=None, label=""):
    run_id = make_run_id(case)
    run_dir = Path("runs") / run_id
    executor = Executor(settings, run_dir, faults=list(faults or []))
    with _video_recording():
        exec_result = executor.run_case(case)
    judge_result = judge_execution(client, case, exec_result, mode="informed")
    report = build_report(
        run_id=run_id,
        case=case,
        exec_result=exec_result,
        judge_result=judge_result,
        run_dir=run_dir,
        halo_image=settings.halo_image,
        llm_model=settings.llm_model,
    )
    write_report(report, Path("reports"))
    verdict = (report.get("judge") or {}).get("verdict")
    print(f"[demo] {label}: run_id={run_id} verdict={verdict}")
    return report


def main() -> int:
    settings = load_settings()
    settings.require_llm_config()
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    client = LLMClient(
        run_id="demo-planner",
        run_dir=Path("runs/_demo_planner"),
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout_s=settings.llm_timeout_s,
    )

    print(f"[demo] planner（grounded）：一句话描述 -> 用例\n  {FEATURE_DESC!r}")
    explorer = Explorer(settings, Path("runs/_demo_explorer"))
    case = plan_case(
        client,
        feature_desc=FEATURE_DESC,
        feature_id=FEATURE_ID,
        explorer=explorer,
        grounding={},
    )
    print(f"[demo] 用例已生成: {case.id}（{len(case.steps)} 步）")

    _run_and_report(settings, client, case, label="健康系统")
    _run_and_report(settings, client, case, faults=[FAULT], label="故障注入")

    videos = sorted(VIDEO_DIR.glob("*.webm"))
    print(f"[demo] 原始录像: {[str(v) for v in videos]}")
    print("[demo] 下一步：用 ffmpeg 剪成 docs/media/demo.gif（见 README）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
