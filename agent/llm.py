"""LLM 适配层：全项目唯一的 LLM 出入口（OpenAI 兼容接口）。

要求（任务包 §0）：
- 模型名 / 温度 / 超时可配（.env）；
- 每次调用记录 prompt hash、token 数、耗时到 runs/<run_id>/calls.jsonl，便于复盘成本；
- 记录里不写 prompt 原文（只记 hash 与长度），避免密钥/隐私进仓库。

不追求通用：只支持 chat.completions + 可选 json 模式，够用即可。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


class LLMError(RuntimeError):
    """LLM 调用失败 / 输出不可解析。"""


@dataclass
class CallRecord:
    ts: str
    run_id: str
    phase: str
    model: str
    temperature: float
    attempt: int
    json_mode: bool
    prompt_hash: str
    prompt_chars: int
    completion_chars: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    ok: bool
    error: str | None


class LLMClient:
    def __init__(
        self,
        *,
        run_id: str,
        run_dir: Path,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        timeout_s: int = 60,
    ) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY 未配置，拒绝发起 LLM 调用（密钥只放 .env）")
        self.run_id = run_id
        self.model = model
        self.temperature = temperature
        # max_retries=0：重试策略由上层（带反馈重规划）显式控制，避免静默加倍成本
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)
        self.calls_path = Path(run_dir) / "calls.jsonl"
        self.calls_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #

    def _log(self, rec: CallRecord) -> None:
        with self.calls_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    @staticmethod
    def _prompt_hash(system: str, user: str) -> str:
        return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()[:16]

    def chat(
        self,
        *,
        phase: str,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        """发起一次补全；json_mode 请求失败时自动降级为普通模式重发一次（两次都记账）。"""
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
        }
        prompt_hash = self._prompt_hash(system, user)

        attempt = 1
        last_error: Exception | None = None
        while attempt <= 2:
            use_json = json_mode and attempt == 1
            if use_json:
                kwargs["response_format"] = {"type": "json_object"}
            elif "response_format" in kwargs:
                del kwargs["response_format"]

            t0 = time.monotonic()
            try:
                resp = self._client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 —— 网络/SDK 异常统一记账后上抛
                last_error = exc
                self._log(
                    CallRecord(
                        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        run_id=self.run_id,
                        phase=phase,
                        model=self.model,
                        temperature=kwargs["temperature"],
                        attempt=attempt,
                        json_mode=use_json,
                        prompt_hash=prompt_hash,
                        prompt_chars=len(system) + len(user),
                        completion_chars=0,
                        prompt_tokens=None,
                        completion_tokens=None,
                        total_tokens=None,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                        ok=False,
                        error=type(exc).__name__ + ": " + str(exc)[:300],
                    )
                )
                # json 模式不被网关支持时降级重试一次；其余错误直接抛
                if json_mode and attempt == 1:
                    attempt += 1
                    continue
                raise LLMError(f"LLM 调用失败（phase={phase}）: {exc}") from exc

            content = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            self._log(
                CallRecord(
                    ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    run_id=self.run_id,
                    phase=phase,
                    model=self.model,
                    temperature=kwargs["temperature"],
                    attempt=attempt,
                    json_mode=use_json,
                    prompt_hash=prompt_hash,
                    prompt_chars=len(system) + len(user),
                    completion_chars=len(content),
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    ok=True,
                    error=None,
                )
            )
            if not content:
                raise LLMError(f"LLM 返回空内容（phase={phase}）")
            return content

        raise LLMError(f"LLM 调用失败（phase={phase}）: {last_error}")

    def chat_json(self, *, phase: str, system: str, user: str, temperature: float | None = None) -> dict:
        """要求模型输出 JSON 并解析；解析失败抛 LLMError（调用方决定降级策略）。"""
        content = self.chat(phase=phase, system=system, user=user, json_mode=True, temperature=temperature)
        try:
            return extract_json(content)
        except ValueError as exc:
            raise LLMError(f"LLM 输出不是合法 JSON（phase={phase}）: {exc}; 原文前200字: {content[:200]!r}") from exc


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 对象（容忍 ``` 围栏与前后废话）。"""
    cleaned = _FENCE_RE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("未找到 JSON 对象")
    return json.loads(cleaned[start : end + 1])


def summarize_calls(calls_path: Path) -> dict:
    """读取 calls.jsonl 汇总成本（report.py 用；失败/空文件返回零值而不是报错）。"""
    summary = {
        "calls_total": 0,
        "calls_failed": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0,
        "by_phase": {},
        "calls_file": str(calls_path),
    }
    if not calls_path.exists():
        return summary
    with calls_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            summary["calls_total"] += 1
            if not rec.get("ok"):
                summary["calls_failed"] += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if isinstance(rec.get(key), int):
                    summary[key] += rec[key]
            summary["latency_ms"] += rec.get("latency_ms", 0)
            phase = rec.get("phase", "?")
            bucket = summary["by_phase"].setdefault(
                phase, {"calls": 0, "total_tokens": 0, "latency_ms": 0}
            )
            bucket["calls"] += 1
            if isinstance(rec.get("total_tokens"), int):
                bucket["total_tokens"] += rec["total_tokens"]
            bucket["latency_ms"] += rec.get("latency_ms", 0)
    return summary
