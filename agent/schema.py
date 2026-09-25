"""结构化用例 schema：受限动作集的唯一定义与校验入口。

设计约束（与任务包一致）：
- steps 只能使用受限动作集 ACTIONS，禁止自由文本步骤；
- 每个动作的必填参数在 schema 层强制（非法输出直接被拒，不会进执行器）；
- 凭据不得明文写在用例里，统一用 {{ADMIN_USER}} / {{ADMIN_PASSWORD}} 占位符，
  执行时由 executor 用 .env 渲染。
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# 受限动作集（8 个，不许扩展）
ACTIONS = (
    "goto",
    "click",
    "fill",
    "select",
    "wait_for",
    "assert_text",
    "assert_visible",
    "assert_url",
)

ActionName = Literal[
    "goto",
    "click",
    "fill",
    "select",
    "wait_for",
    "assert_text",
    "assert_visible",
    "assert_url",
]

ASSERT_ACTIONS = frozenset({"assert_text", "assert_visible", "assert_url"})

# 用例 JSON 中允许的模板变量（executor 渲染，报告写回占位符原文以避免泄密）
# RUN_ID：每次执行唯一的短串，用于必须唯一的测试数据（分类别名、标签别名等），
# 让同一条用例可以重复执行而不因"已存在"失败（测试数据隔离）
TEMPLATE_VARS = frozenset({"BASE_URL", "ADMIN_USER", "ADMIN_PASSWORD", "RUN_ID"})

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


class Step(BaseModel):
    """单步动作。字段按动作裁剪：多余/缺失参数都会被拒。"""

    model_config = ConfigDict(extra="forbid")

    action: ActionName
    selector: str | None = None
    text: str | None = None
    value: str | None = None
    url: str | None = None
    timeout_ms: int | None = None

    @model_validator(mode="after")
    def _check_required_params(self) -> Step:
        a = self.action
        if a == "goto" and not self.url:
            raise ValueError("goto 需要参数 url")
        if a == "click" and not self.selector:
            raise ValueError("click 需要参数 selector")
        if a == "fill" and (not self.selector or self.value is None):
            raise ValueError("fill 需要参数 selector 和 value")
        if a == "select" and (not self.selector or self.value is None):
            raise ValueError("select 需要参数 selector 和 value")
        if a == "wait_for" and not self.selector and not self.text:
            raise ValueError("wait_for 需要 selector 或 text 至少一个")
        if a == "assert_text" and not self.text:
            raise ValueError("assert_text 需要参数 text（selector 可选，用于限定范围）")
        if a == "assert_visible" and not self.selector:
            raise ValueError("assert_visible 需要参数 selector")
        if a == "assert_url" and not self.url:
            raise ValueError("assert_url 需要参数 url")
        return self

    @field_validator("selector", "text", "value", "url")
    @classmethod
    def _check_template_vars(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # 只允许白名单占位符，避免用例里出现真实凭据
        for raw in re.findall(r"\{\{\s*(\w+)\s*\}\}", v):
            if raw not in TEMPLATE_VARS:
                raise ValueError(
                    f"未知模板变量 {{{{{raw}}}}}，只允许: {sorted(TEMPLATE_VARS)}"
                )
        return v

    def params(self) -> dict[str, str]:
        """该动作实际用到的参数（用于日志与报告；报告里写的是占位符原文）。"""
        out: dict[str, str] = {}
        for key in ("selector", "text", "value", "url"):
            v = getattr(self, key)
            if v is not None:
                out[key] = v
        return out


class Case(BaseModel):
    """一条结构化用例。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    priority: Literal["P0", "P1", "P2"]
    preconditions: list[str] = []
    steps: list[Step]
    expected: list[str]
    # Agent 生成用例时必须带 feature_id（bench 按 feature_id 人工映射算覆盖率）；
    # 手写用例可选。
    feature_id: str | None = None

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(f"case id 必须匹配 {_ID_RE.pattern}，当前: {v!r}")
        return v

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title 不能为空")
        return v

    @field_validator("steps")
    @classmethod
    def _check_steps(cls, v: list[Step]) -> list[Step]:
        if not v:
            raise ValueError("steps 不能为空")
        return v

    @field_validator("expected")
    @classmethod
    def _check_expected(cls, v: list[str]) -> list[str]:
        v = [s.strip() for s in v if s.strip()]
        if not v:
            raise ValueError("expected 不能为空")
        return v
