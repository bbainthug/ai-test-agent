"""集中配置：全部来自环境变量 / .env。

约定：
- 密钥只进 .env（已被 .gitignore 排除），任何报告/日志写入仓库前必须先脱敏。
- 所有可调参数（模型名、温度、超时、定位超时）都可由环境变量覆盖。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """配置缺失或非法。"""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须是整数，当前值: {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须是数字，当前值: {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"环境变量 {name} 必须是布尔值，当前值: {raw!r}")


@dataclass(frozen=True)
class Settings:
    # LLM（OpenAI 兼容）
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float
    llm_timeout_s: int
    # Halo 靶子
    halo_base_url: str
    halo_admin_user: str
    halo_admin_password: str
    halo_image: str
    # 执行器
    step_timeout_ms: int
    goto_timeout_ms: int
    headless: bool
    blocked_hosts: tuple[str, ...]

    @property
    def secrets(self) -> set[str]:
        """需要从快照/日志/报告中脱敏的字符串（只保留非空值）。"""
        return {v for v in (self.halo_admin_password,) if len(v) >= 4}

    def require_llm_config(self) -> None:
        """需要真正发起 LLM 调用时才校验（--skip-judge 纯断言路径不依赖 LLM）。"""
        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL", self.llm_base_url),
                ("LLM_API_KEY", self.llm_api_key),
                ("LLM_MODEL", self.llm_model),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "缺少 LLM 配置: " + ", ".join(missing)
                + "。请参考 .env.example 填写 .env（密钥只进 .env，不进仓库）。"
            )

    def template_vars(self) -> dict[str, str]:
        """用例 JSON 中 {{VAR}} 占位符的渲染来源。"""
        return {
            "BASE_URL": self.halo_base_url.rstrip("/"),
            "ADMIN_USER": self.halo_admin_user,
            "ADMIN_PASSWORD": self.halo_admin_password,
        }


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    # 显式传入路径或按 cwd 查找 .env；找不到也不报错，允许纯环境变量运行
    load_dotenv(env_file if env_file is not None else Path(".env"))

    base_url = os.getenv("LLM_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()

    halo_base_url = os.getenv("HALO_BASE_URL", "http://localhost:8090").strip().rstrip("/")
    halo_user = os.getenv("HALO_ADMIN_USER", "").strip()
    halo_password = os.getenv("HALO_ADMIN_PASSWORD", "")

    missing = [
        name
        for name, value in (
            ("HALO_ADMIN_USER", halo_user),
            ("HALO_ADMIN_PASSWORD", halo_password),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            "缺少必要配置: " + ", ".join(missing) + "。请参考 .env.example 创建 .env。"
        )

    step_timeout_ms = _env_int("STEP_TIMEOUT_MS", 8000)
    if step_timeout_ms <= 0:
        raise ConfigError("STEP_TIMEOUT_MS 必须为正整数")

    return Settings(
        llm_base_url=base_url,
        llm_api_key=api_key,
        llm_model=model,
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.0),
        llm_timeout_s=_env_int("LLM_TIMEOUT_S", 60),
        halo_base_url=halo_base_url,
        halo_admin_user=halo_user,
        halo_admin_password=halo_password,
        halo_image=os.getenv("HALO_IMAGE", "registry.fit2cloud.com/halo/halo:2.20").strip(),
        step_timeout_ms=step_timeout_ms,
        goto_timeout_ms=_env_int("GOTO_TIMEOUT_MS", 20000),
        headless=_env_bool("HEADLESS", True),
        blocked_hosts=tuple(
            h.strip()
            for h in os.getenv("BLOCK_EXTERNAL_HOSTS", "").split(",")
            if h.strip()
        ),
    )
