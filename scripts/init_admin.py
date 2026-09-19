"""初始化 Halo 管理员（幂等）。由 scripts/up.sh 调用；也可单独执行。

只依赖标准库。凭据从环境变量读取（HALO_ADMIN_USER / HALO_ADMIN_PASSWORD），
不落盘、不打印明文。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.getenv("HALO_BASE_URL", "http://localhost:8090").rstrip("/")
SETUP_API = "/apis/api.console.halo.run/v1alpha1/system-setup"
READYNESS = "/actuator/health/readiness"

UA = {"Content-Type": "application/json", "User-Agent": "ai-test-agent/0.1"}


def _request(method: str, path: str, body: dict | None = None, timeout: int = 10):
    req = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=UA,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def wait_ready(max_wait_s: int = 240) -> bool:
    """等待 /actuator/health/readiness 返回 200。"""
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        code, _ = _request("GET", READYNESS)
        if code == 200:
            return True
        time.sleep(2)
    return False


def system_setup(username: str, password: str) -> str:
    """调用初始化接口。返回 'created' | 'already' | 'error:...'。"""
    code, text = _request(
        "POST",
        SETUP_API,
        {
            "username": username,
            "password": password,
            "confirmPassword": password,
        },
    )
    if code in (200, 201):
        return "created"
    body = text[:400]
    # 已初始化的幂等出口：接口会明确报错而不是静默成功
    if code in (400, 403, 409) and (
        "initialized" in body.lower() or "已初始化" in body or "已存在" in body
    ):
        return "already"
    return f"error: HTTP {code}: {body}"


def main() -> int:
    user = os.getenv("HALO_ADMIN_USER", "").strip()
    password = os.getenv("HALO_ADMIN_PASSWORD", "")
    if not user or not password:
        print("[init-admin] 缺少 HALO_ADMIN_USER / HALO_ADMIN_PASSWORD 环境变量")
        return 2

    print("[init-admin] 等待系统就绪…")
    if not wait_ready():
        print("[init-admin] 就绪检查超时，请查看容器日志")
        return 1

    result = system_setup(user, password)
    if result == "created":
        print("[init-admin] 管理员已初始化")
        return 0
    if result == "already":
        print("[init-admin] 系统已初始化过，跳过")
        return 0
    print(f"[init-admin] 初始化失败: {result}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
