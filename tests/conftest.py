"""单元测试共用的假对象：不启动浏览器、不调用真实 LLM。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeLLM:
    """按顺序返回预设 JSON 的假客户端；raise_with 设为异常则抛出。"""

    def __init__(self, responses=None, raise_with: Exception | None = None):
        self.responses = list(responses or [])
        self.raise_with = raise_with
        self.calls: list[dict] = []

    def chat_json(self, *, phase: str, system: str, user: str, temperature=None) -> dict:
        self.calls.append({"phase": phase, "system": system, "user": user})
        if self.raise_with:
            raise self.raise_with
        return self.responses.pop(0)


class FakeScope:
    """记录选择器解析走了哪个 Playwright 方法。"""

    def __init__(self, path: tuple = ()):
        self.path = path

    def _child(self, how, *args, **kwargs):
        return FakeScope(self.path + ((how, args, tuple(sorted(kwargs.items()))),))

    def get_by_role(self, role, **kw):
        return self._child("role", role, **kw)

    def get_by_label(self, v):
        return self._child("label", v)

    def get_by_text(self, v):
        return self._child("text", v)

    def get_by_placeholder(self, v):
        return self._child("placeholder", v)

    def get_by_test_id(self, v):
        return self._child("testid", v)

    def locator(self, v):
        return self._child("locator", v)
