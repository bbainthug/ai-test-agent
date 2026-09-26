import json
from types import SimpleNamespace

import pytest

import agent.llm as llm_mod
from agent.llm import LLMClient, LLMError


class _Err(Exception):
    def __init__(self, status_code, msg):
        super().__init__(msg)
        self.status_code = status_code


def _resp(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _client(tmp_path, outcomes, monkeypatch):
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    c = LLMClient(run_id="t", run_dir=tmp_path, base_url="http://x", api_key="k", model="m")
    seq = iter(outcomes)

    def create(**kwargs):
        o = next(seq)
        if isinstance(o, Exception):
            raise o
        return o

    c._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return c


def _calls(tmp_path):
    return [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]


def test_rate_limit_is_retried_with_backoff_and_every_attempt_is_logged(tmp_path, monkeypatch):
    rl = _Err(429, "Error code: 429 - {'code': '1302', 'message': '您的账户已达到速率限制'}")
    c = _client(tmp_path, [rl, rl, _resp('{"ok": true}')], monkeypatch)
    assert c.chat_json(phase="p", system="s", user="u") == {"ok": True}
    calls = _calls(tmp_path)
    assert [r["ok"] for r in calls] == [False, False, True]
    assert calls[-1]["json_mode"] is True  # 限速重试不应顺带把 json 模式降级


def test_insufficient_balance_429_is_not_retried(tmp_path, monkeypatch):
    quota = _Err(429, "Error code: 429 - {'code': '1113', 'message': '余额不足或无可用资源包'}")
    c = _client(tmp_path, [quota, _resp('{"ok": true}')], monkeypatch)
    with pytest.raises(LLMError):
        c.chat_json(phase="p", system="s", user="u")
    assert len(_calls(tmp_path)) == 1


def test_rate_limit_gives_up_after_backoff_table(tmp_path, monkeypatch):
    rl = _Err(429, "rate limited")
    n = len(llm_mod.RATE_LIMIT_BACKOFF_S) + 1
    c = _client(tmp_path, [rl] * n, monkeypatch)
    with pytest.raises(LLMError):
        c.chat(phase="p", system="s", user="u")
    assert len(_calls(tmp_path)) == n
