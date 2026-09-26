"""集成测试：探索器在真实 Halo 上工作（需要本地 Halo，默认跳过）。

运行方式：HALO_UP=1 uv run pytest tests/test_explorer_halo_integration.py -m halo
"""

from __future__ import annotations

import os
import urllib.request

import pytest

from agent.config import load_settings
from agent.explorer import Explorer

pytestmark = pytest.mark.halo


def _halo_up() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:8090/actuator/health/readiness", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
def settings():
    if os.getenv("HALO_UP") != "1" or not _halo_up():
        pytest.skip("Halo 未运行（设置 HALO_UP=1 且启动本地 Halo 后运行）")
    return load_settings()


def test_site_map_contains_core_entries(tmp_path, settings):
    ex = Explorer(settings, tmp_path / "explorer")
    sm = ex.site_map()
    console_texts = {e["text"] for e in sm["console"]}
    site_texts = {e["text"] for e in sm["site"]}
    # 控制台侧边栏应有这些核心入口（自动发现，非硬编码路由）
    assert any("文章" in t for t in console_texts), console_texts
    assert any("用户" in t for t in console_texts), console_texts
    assert any("仪表盘" in t or "控制台" in t for t in console_texts | site_texts)
    assert all(e["url"].startswith(settings.halo_base_url) for g in ("console", "site") for e in sm[g])


def test_page_snapshot_and_readonly_expand(tmp_path, settings):
    ex = Explorer(settings, tmp_path / "explorer2")
    sm = ex.site_map()
    posts = next(e for e in sm["console"] if "文章" in e["text"])
    snap = ex.page_snapshot(posts["url"])
    assert len(snap) > 100
    assert "TRUNCATED" not in snap or len(snap) > 5000  # 截断仅在超长时
    # 提交类按钮拒绝点击（只读红线）
    from agent.explorer import ExplorerError

    with pytest.raises(ExplorerError):
        ex.expanded_snapshot(posts["url"], "保存")
