"""录制并剪出 docs/media/demo.gif：一句话功能描述 -> planner 生成用例 ->
浏览器执行 -> 裁判结论 -> 报告；再故障注入重跑一次看裁判判 fail。

不改 agent/ 的任何逻辑——只按公开 API 组合调用 planner/executor/judge/report
（与 agent/run.py、bench/run_bench.py 的调用方式相同），录像通过给
playwright.sync_api.Browser.new_context 打补丁临时注入 record_video_dir 实现，
补丁只在本脚本进程内、Executor.run_case 期间生效，用完即还原，不写回任何库文件。

字幕内容不手写：两次真实运行各自的 reports/<run_id>.json 落盘后，脚本重新从磁盘
读回这两份报告，字幕文字（用例步骤、裁判结论与理由、故障接口）全部从里面取。

去掉执行录像里的空白/静止片段：用 ffmpeg 的 mpdecimate 过滤器丢掉与前一帧
（近似）相同的帧、再用 setpts 把时间轴压缩回去——静止的部分自然被"跳过"，
不需要手动标注该剪哪一段。

依赖：除项目已有依赖外，还需要 Pillow（渲染中文字幕帧，见 pyproject.toml
dev 组）和系统里的一个中文字体（默认找 macOS 自带的 STHeiti；换机器需要改
`_FONT_CANDIDATES`）。

用法（需要 Halo 已通过 ./scripts/up.sh 起好、.env 配好 LLM_API_KEY）：
  uv run python scripts/record_demo.py
输出：
  runs/_demo_video/<run_id>/*.webm   两段原始录像（健康 / 故障注入）
  reports/<run_id>.*                 两条真实报告（与仓库其余报告同一套产出路径）
  docs/media/demo.gif                最终演示 GIF
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import playwright.sync_api as pw
from PIL import Image, ImageDraw, ImageFont

from agent.config import load_settings
from agent.executor import Executor, Fault
from agent.explorer import Explorer
from agent.judge import judge_execution
from agent.llm import LLMClient
from agent.planner import plan_case
from agent.report import build_report, write_report
from agent.run import make_run_id

# ---- 可调参数（想改画面效果只用动这一块） -------------------------------
VIDEO_DIR = Path("runs/_demo_video")
BUILD_DIR = Path("runs/_demo_build")
GIF_OUT = Path("docs/media/demo.gif")
FRAME_SIZE = (1440, 900)  # 与 Executor 里 new_context 的 viewport 一致
FPS = 10
GIF_WIDTH = 880
CAPTION_BG = (16, 18, 22)
CAPTION_FG = (240, 240, 240)
CAPTION_ACCENT_PASS = (110, 210, 140)
CAPTION_ACCENT_FAIL = (230, 110, 110)
_FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",  # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # 常见 Linux 路径
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

FEATURE_DESC = "登录后在系统设置里修改站点标题并保存，前台首页显示新标题"
FEATURE_ID = "site-title"
# 与 bench/features.json 里 site-title 的故障定义一致
FAULT = Fault(url_regex=r"/api/v1alpha1/configmaps/system", status=500, method="PUT")


# ---- 录制：健康 / 故障注入两次真实运行 ------------------------------------


@contextlib.contextmanager
def _video_recording(video_dir: Path):
    """临时给 Browser.new_context 打补丁注入录像目录；退出时还原。"""
    orig = pw.Browser.new_context

    def patched(self, **kwargs):
        kwargs.setdefault("record_video_dir", str(video_dir))
        kwargs.setdefault("record_video_size", {"width": FRAME_SIZE[0], "height": FRAME_SIZE[1]})
        return orig(self, **kwargs)

    pw.Browser.new_context = patched
    try:
        yield
    finally:
        pw.Browser.new_context = orig


def _run_and_report(settings, client, case, *, faults=None, label="") -> tuple[str, Path]:
    run_id = make_run_id(case)
    run_dir = Path("runs") / run_id
    video_dir = VIDEO_DIR / run_id
    video_dir.mkdir(parents=True, exist_ok=True)
    executor = Executor(settings, run_dir, faults=list(faults or []))
    with _video_recording(video_dir):
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
    json_path, _ = write_report(report, Path("reports"))
    verdict = (report.get("judge") or {}).get("verdict")
    print(f"[demo] {label}: run_id={run_id} verdict={verdict}")
    return run_id, json_path


def _find_video(video_dir: Path) -> Path:
    videos = sorted(video_dir.glob("*.webm"))
    if not videos:
        raise RuntimeError(f"没在 {video_dir} 找到录像文件")
    return videos[0]


# ---- 字幕：从落盘的报告 JSON 里取文字，不手写 -----------------------------


def _load_report(path: Path) -> dict:
    """字幕内容的唯一来源：重新从磁盘读回刚写的报告 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise RuntimeError(
        "找不到可用的中文字体，请在 scripts/record_demo.py 的 _FONT_CANDIDATES 里加一条本机路径"
    )


def _wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=True) or [text]


def _caption_lines_feature() -> list[tuple[str, tuple[int, int, int], int]]:
    """(文字, 颜色, 字号) 三元组列表，按行画。"""
    return [
        ("功能描述", CAPTION_FG, 34),
        *[(line, CAPTION_FG, 46) for line in _wrap(FEATURE_DESC, 18)],
    ]


def _caption_lines_planner(report: dict) -> list[tuple[str, tuple[int, int, int], int]]:
    case = report["case"]
    steps = case["steps"]
    lines: list[tuple[str, tuple[int, int, int], int]] = [
        (f"planner 生成用例：{case['title']}", CAPTION_FG, 34),
        (f"共 {len(steps)} 步（grounded：先探索真实页面再写用例）", CAPTION_FG, 26),
        ("", CAPTION_FG, 10),
    ]
    for i, step in enumerate(steps[:6], start=1):
        detail = step.get("selector") or step.get("url") or step.get("text") or ""
        value = f" = {step['value']}" if step.get("value") else ""
        lines.append((f"{i}. {step['action']} {detail}{value}", CAPTION_FG, 24))
    if len(steps) > 6:
        lines.append((f"...（还有 {len(steps) - 6} 步）", CAPTION_FG, 22))
    return lines


def _caption_lines_judge(report: dict, *, passed: bool) -> list[tuple[str, tuple[int, int, int], int]]:
    judge = report.get("judge") or {}
    verdict = (judge.get("verdict") or "?").upper()
    accent = CAPTION_ACCENT_PASS if passed else CAPTION_ACCENT_FAIL
    lines: list[tuple[str, tuple[int, int, int], int]] = [
        (f"裁判：{verdict}", accent, 56),
        ("", CAPTION_FG, 10),
    ]
    reason = judge.get("reason") or "（无理由文本）"
    for line in _wrap(reason, 26)[:6]:
        lines.append((line, CAPTION_FG, 26))
    return lines


def _caption_lines_fault(report: dict) -> list[tuple[str, tuple[int, int, int], int]]:
    faults = report.get("execution", {}).get("faults") or []
    if faults:
        f = faults[0]
        method = f.get("method") or "*"
        detail = f"{method} {f['url_regex']} -> HTTP {f['status']}"
    else:
        detail = "(未在报告里找到 faults 字段)"
    return [
        ("注入故障", CAPTION_ACCENT_FAIL, 34),
        *[(line, CAPTION_FG, 32) for line in _wrap(detail, 24)],
        ("", CAPTION_FG, 10),
        ("Playwright route() 拦截该接口直接返回上面的状态码", CAPTION_FG, 22),
    ]


def _render_caption_png(lines: list[tuple[str, tuple[int, int, int], int]], out_path: Path) -> None:
    img = Image.new("RGB", FRAME_SIZE, CAPTION_BG)
    draw = ImageDraw.Draw(img)
    heights = []
    rendered = []
    for text, color, size in lines:
        if not text:
            heights.append(size)
            rendered.append((None, color, size))
            continue
        font = _font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        heights.append(bbox[3] - bbox[1])
        rendered.append((font, color, size, text))
    total_h = sum(heights) + 14 * (len(lines) - 1)
    y = (FRAME_SIZE[1] - total_h) // 2
    for item, h in zip(rendered, heights, strict=True):
        if item[0] is None:
            y += h + 14
            continue
        font, color, _size, text = item
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        x = (FRAME_SIZE[0] - w) // 2
        draw.text((x, y), text, font=font, fill=color)
        y += h + 14
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


# ---- ffmpeg 管线：字幕帧 -> 短片；执行录像去静止；全部拼接；出 GIF --------


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _caption_clip(png_path: Path, duration: float, out_path: Path) -> None:
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(png_path),
        "-t", str(duration), "-r", str(FPS),
        "-vf", f"scale={FRAME_SIZE[0]}:{FRAME_SIZE[1]}",
        "-pix_fmt", "yuv420p", str(out_path),
    ])


def _decimated_clip(webm_path: Path, out_path: Path) -> None:
    """丢掉与前一帧近似相同的帧、把时间轴压缩回去，去掉空白/静止片段。"""
    vf = (
        f"mpdecimate=hi=120:lo=48:frac=0.2,setpts=N/FRAME_RATE/TB,"
        f"scale={FRAME_SIZE[0]}:{FRAME_SIZE[1]}"
    )
    _run([
        "ffmpeg", "-y", "-i", str(webm_path),
        "-vf", vf,
        "-r", str(FPS), "-pix_fmt", "yuv420p", str(out_path),
    ])


def _concat(clips: list[Path], out_path: Path) -> None:
    """重新编码拼接（不用 `-c copy`）：caption 片段（来自 PNG）与录像解密后的片段
    色彩范围/像素格式元数据不完全一致，流拷贝拼接在这台机器的 ffmpeg 上会在
    paletteuse 阶段触发 "Internal bug, should not have happened" 崩溃；统一
    重新编码成同一种格式后再拼接可以避免这个问题，反正片段都很小。
    """
    list_file = BUILD_DIR / "concat_list.txt"
    list_file.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-vf", f"scale={FRAME_SIZE[0]}:{FRAME_SIZE[1]},fps={FPS}",
        "-color_range", "tv", "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", str(out_path),
    ])


def _to_gif(mp4_path: Path, out_path: Path) -> None:
    palette = BUILD_DIR / "palette.png"
    _run([
        "ffmpeg", "-y", "-i", str(mp4_path),
        "-vf", f"fps={FPS},scale={GIF_WIDTH}:-1:flags=lanczos,palettegen=max_colors=192",
        str(palette),
    ])
    _run([
        "ffmpeg", "-y", "-i", str(mp4_path), "-i", str(palette),
        "-lavfi", f"fps={FPS},scale={GIF_WIDTH}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
        "-loop", "0", str(out_path),
    ])


def build_gif(healthy_report_path: Path, healthy_video_dir: Path,
              fault_report_path: Path, fault_video_dir: Path) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    healthy_report = _load_report(healthy_report_path)
    fault_report = _load_report(fault_report_path)

    segments: list[Path] = []

    def add_caption(name: str, lines: list[tuple[str, tuple[int, int, int], int]]) -> None:
        # 按非空行数给阅读时间：字幕行数会随用例步数/裁判理由长度变化，
        # 固定时长要么读不完要么等太久——2.4s 起步，每多一行加 0.55s，封顶 8s。
        n = sum(1 for text, *_ in lines if text)
        duration = min(8.0, max(2.4, 1.5 + 0.55 * n))
        png = BUILD_DIR / f"{name}.png"
        clip = BUILD_DIR / f"{name}.mp4"
        _render_caption_png(lines, png)
        _caption_clip(png, duration, clip)
        segments.append(clip)

    add_caption("c1_feature", _caption_lines_feature())
    add_caption("c2_planner", _caption_lines_planner(healthy_report))

    healthy_clip = BUILD_DIR / "v1_healthy.mp4"
    _decimated_clip(_find_video(healthy_video_dir), healthy_clip)
    segments.append(healthy_clip)

    add_caption("c3_judge_pass", _caption_lines_judge(healthy_report, passed=True))
    add_caption("c4_fault", _caption_lines_fault(fault_report))

    fault_clip = BUILD_DIR / "v2_fault.mp4"
    _decimated_clip(_find_video(fault_video_dir), fault_clip)
    segments.append(fault_clip)

    add_caption("c5_judge_fail", _caption_lines_judge(fault_report, passed=False))

    combined = BUILD_DIR / "combined.mp4"
    _concat(segments, combined)
    _to_gif(combined, GIF_OUT)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(combined)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    size_mb = GIF_OUT.stat().st_size / 1024 / 1024
    print(f"[demo] {GIF_OUT}: {duration:.1f}s, {size_mb:.2f} MiB")


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

    healthy_id, healthy_report_path = _run_and_report(settings, client, case, label="健康系统")
    fault_id, fault_report_path = _run_and_report(settings, client, case, faults=[FAULT], label="故障注入")

    build_gif(
        healthy_report_path, VIDEO_DIR / healthy_id,
        fault_report_path, VIDEO_DIR / fault_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
