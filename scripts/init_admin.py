"""初始化 Halo 管理员（幂等）。由 scripts/up.sh 调用；也可单独执行。

真实契约（Halo 2.20.x 实测）：
- 未初始化时 GET / 302 跳 /system/setup，初始化后 GET / 返回 200；
- 初始化表单：GET /system/setup 取 cookie + _csrf，表单 POST 回 /system/setup
  （字段 language/siteTitle/username/email/password/confirmPassword + _csrf），成功返回 204。

只依赖标准库。凭据从环境变量读取（HALO_ADMIN_USER / HALO_ADMIN_PASSWORD），
不落盘、不打印明文；站点标题与邮箱使用合成测试数据。
"""

from __future__ import annotations

import http.cookiejar
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.getenv("HALO_BASE_URL", "http://localhost:8090").rstrip("/")
SETUP_PAGE = "/system/setup"
READYNESS = "/actuator/health/readiness"
UA = {"User-Agent": "ai-test-agent/0.1"}


class Http:
    """带 cookie 的极简 HTTP 客户端（标准库，避免给脚本加依赖）。"""

    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path: str) -> tuple[int, str, str]:
        req = urllib.request.Request(BASE_URL + path, headers=UA, method="GET")
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8", "replace"), resp.geturl()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), exc.geturl()

    def post_form(self, path: str, fields: dict[str, str]) -> tuple[int, str]:
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(
            BASE_URL + path, data=data, method="POST",
            headers={**UA, "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")


def wait_ready(max_wait_s: int = 240) -> bool:
    """等待 /actuator/health/readiness 返回 200。"""
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        code, _, _ = Http().get(READYNESS)
        if code == 200:
            return True
        time.sleep(2)
    return False


def is_initialized(http: Http) -> bool:
    """GET / 是否已不再跳转 /system/setup。"""
    code, _, final_url = http.get("/")
    return code == 200 and SETUP_PAGE not in final_url


def setup_admin(http: Http, username: str, password: str) -> str:
    """提交初始化表单。返回 'created' | 'error:...'。"""
    code, page, _ = http.get(SETUP_PAGE)
    if code != 200:
        return f"error: GET {SETUP_PAGE} -> HTTP {code}"
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', page)
    if not m:
        return "error: 未在 setup 页面找到 _csrf"
    fields = {
        "_csrf": m.group(1),
        "language": "zh-CN",
        "siteTitle": "Agent 测试站",
        "username": username,
        "email": "agent-test@example.com",
        "password": password,
        "confirmPassword": password,
    }
    code, body = http.post_form(SETUP_PAGE, fields)
    if code in (200, 201, 204, 302):
        return "created"
    return f"error: POST -> HTTP {code}: {body[:300]}"


def main() -> int:
    user = os.getenv("HALO_ADMIN_USER", "").strip()
    password = os.getenv("HALO_ADMIN_PASSWORD", "")
    if not user or not password:
        print("[init-admin] 缺少 HALO_ADMIN_USER / HALO_ADMIN_PASSWORD 环境变量")
        return 2

    print("[init-admin] 等待系统就绪…")
    if not wait_ready():
        print("[init-admin] 就绪检查超时，请查看容器日志（docker logs ai-test-agent-halo）")
        return 1

    http = Http()
    if is_initialized(http):
        print("[init-admin] 系统已初始化过，跳过")
        return 0

    result = setup_admin(http, user, password)
    if result == "created" and is_initialized(http):
        print("[init-admin] 管理员已初始化（站点标题/邮箱为合成测试数据）")
        return 0
    print(f"[init-admin] 初始化失败: {result}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
