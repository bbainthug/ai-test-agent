"""B2 单元测试：探索器纯函数、静态选择器校验、grounded planner（FakeLLM）。"""

from __future__ import annotations

import threading
from contextlib import contextmanager

import pytest
from conftest import FakeLLM

import agent.explorer as explorer_module
from agent.config import Settings
from agent.explorer import Explorer, _links_from_aria, is_submit_button
from agent.planner import (
    PlannerError,
    parse_snapshot_entries,
    plan_case,
    validate_selectors,
)

ARIA_FIXTURE = """
- banner:
  - link "Halo":
    - /url: http://localhost:8090/console/dashboard
  - link "文档":
    - /url: https://docs.halo.run
- navigation:
  - link "文章":
    - /url: /console/posts
  - link "用户":
    - /url: /console/users?tab=detail
  - link "文章":
    - /url: /console/posts
"""


# ---------------------------------------------------------------------------
# 站点地图提取（aria 快照 fixture）
# ---------------------------------------------------------------------------


def test_links_from_aria_fixture():
    # 返回 [{text, url}]：相对路径拼 base，站外丢弃、重复 URL 去重
    links = _links_from_aria(ARIA_FIXTURE, "http://localhost:8090")
    by_url = {l["url"]: l for l in links}
    assert "http://localhost:8090/console/posts" in by_url
    assert "http://localhost:8090/console/users?tab=detail" in by_url
    assert "http://localhost:8090/console/dashboard" in by_url
    assert all("docs.halo.run" not in u for u in by_url)
    assert len(by_url) == 3  # 重复的 /console/posts 只留一条
    assert by_url["http://localhost:8090/console/posts"]["text"] == "文章"


# ---------------------------------------------------------------------------
# 并发安全：多个规划线程共用一个 Explorer 实例时，site_map() 只真正探索一次
# ---------------------------------------------------------------------------


def _fake_settings() -> Settings:
    return Settings(
        llm_base_url="http://fake", llm_api_key="x", llm_model="x",
        llm_temperature=0.0, llm_timeout_s=10,
        halo_base_url="http://localhost:8090", halo_admin_user="admin",
        halo_admin_password="secretpw123", halo_image="x",
        step_timeout_ms=1000, goto_timeout_ms=1000, headless=True, blocked_hosts=(),
    )


class _FakePage:
    def goto(self, *a, **kw):
        pass

    def wait_for_timeout(self, *a, **kw):
        pass

    def new_page(self):
        return self


class _FakeBrowserOrContext:
    def new_page(self):
        return _FakePage()

    def close(self):
        pass


def test_concurrent_site_map_calls_explore_only_once(monkeypatch, tmp_path):
    """8 个线程同时调用 site_map()：真正的探索逻辑（_extract_links）只跑一次。"""
    calls = {"n": 0}
    call_lock = threading.Lock()

    def fake_extract_links(page, base_url):
        with call_lock:
            calls["n"] += 1
        return [{"text": f"页{calls['n']}", "url": f"{base_url}/p{calls['n']}"}]

    @contextmanager
    def fake_sync_playwright():
        yield object()

    monkeypatch.setattr(explorer_module, "sync_playwright", fake_sync_playwright)
    monkeypatch.setattr(explorer_module, "_extract_links", fake_extract_links)
    monkeypatch.setattr(
        Explorer, "_new_context", lambda self, p: (_FakeBrowserOrContext(), _FakeBrowserOrContext())
    )
    monkeypatch.setattr(Explorer, "_login_and_save", lambda self: None)

    ex = Explorer(_fake_settings(), tmp_path / "explorer")
    barrier = threading.Barrier(8)
    results: list[dict | None] = [None] * 8

    def worker(idx: int) -> None:
        barrier.wait()
        results[idx] = ex.site_map()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # site_map() 每次真正探索调用 _extract_links 两次（console + site）；
    # 不管多少线程并发调用，一次运行只应该探索一次 = 总共 2 次，不是 16 次。
    assert calls["n"] == 2, f"应该只探索一次（2 次 _extract_links 调用），实际 {calls['n']}"
    assert all(r == results[0] for r in results), "并发调用必须返回同一份站点地图"


def test_submit_button_blacklist():
    for name in ("保存", "保存并继续添加", "提交", "发布", "删除", "确定", "创建",
                 "确认删除", "还原设置", "清空回收站"):
        assert is_submit_button(name), name
    for name in ("新建", "展开", "下一步", "文章设置", "重命名输入"):
        assert not is_submit_button(name), name


# ---------------------------------------------------------------------------
# 静态选择器校验
# ---------------------------------------------------------------------------

SNAPSHOT = """
- banner:
  - heading "内容"
  - link "文章"
- main:
  - button "保存并继续添加"
  - button "发布"
  - textbox "请输入标题"
  - dialog "文章设置":
    - textbox "别名"
"""


def _case(steps):
    return {
        "id": "test-case", "feature_id": "t", "title": "t", "priority": "P1",
        "steps": steps, "expected": ["x"],
    }


def test_validate_role_name_exact_match():
    from agent.schema import Case
    ok = Case.model_validate(_case([
        {"action": "click", "selector": 'role=button[name="发布"]'},
    ]))
    assert validate_selectors(ok, SNAPSHOT) == []
    # "保存" 是 "保存并继续添加" 的子串：精确匹配必须判违例
    bad = Case.model_validate(_case([
        {"action": "click", "selector": 'role=button[name="保存"]'},
    ]))
    v = validate_selectors(bad, SNAPSHOT)
    assert len(v) == 1 and "保存" in v[0] and "精确" in v[0]


def test_validate_chain_and_css_skip():
    from agent.schema import Case
    # >> 链式：两段都在快照里
    ok = Case.model_validate(_case([
        {"action": "click", "selector": 'role=dialog[name="文章设置"] >> role=textbox[name="别名"]'},
    ]))
    assert validate_selectors(ok, SNAPSHOT) == []
    # CSS / placeholder / testid / xpath 跳过校验
    ok2 = Case.model_validate(_case([
        {"action": "click", "selector": "css=.vanishing-never-exists"},
        {"action": "fill", "selector": "placeholder=搜索", "value": "x"},
        {"action": "click", "selector": "//div[@id='nope']"},
    ]))
    assert validate_selectors(ok2, SNAPSHOT) == []


def test_validate_text_and_wait_for():
    from agent.schema import Case
    ok = Case.model_validate(_case([
        {"action": "wait_for", "text": "文章"},
    ]))
    assert validate_selectors(ok, SNAPSHOT) == []
    bad = Case.model_validate(_case([
        {"action": "wait_for", "text": "不存在的文案"},
        {"action": "assert_visible", "selector": 'role=button[name="不存在的按钮"]'},
    ]))
    v = validate_selectors(bad, SNAPSHOT)
    assert len(v) == 2


def test_parse_snapshot_entries_shapes():
    entries = parse_snapshot_entries(SNAPSHOT)
    assert ("button", "发布") in entries
    assert ("dialog", "文章设置") in entries
    assert ("textbox", "请输入标题") in entries


# ---------------------------------------------------------------------------
# grounded planner（FakeLLM，不启动浏览器）
# ---------------------------------------------------------------------------


SITE_MAP_TEXT = "## 控制台导航\n- 文章 → http://localhost:8090/console/posts\n"

PAGE_SNAPSHOT = """
- main:
  - heading "文章列表"
  - textbox "请输入标题"
  - button "发布"
"""


class FakeExplorer:
    """grounded 路径的假探索器：固定站点地图与快照，可注入失败。"""

    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.calls: list[str] = []

    def site_map_text(self) -> str:
        self.calls.append("site_map")
        if self.fail:
            raise self.fail
        return SITE_MAP_TEXT

    def page_snapshot(self, url: str, max_chars: int = 12000) -> str:
        self.calls.append(f"snapshot:{url}")
        if self.fail:
            raise self.fail
        return PAGE_SNAPSHOT

    def expanded_snapshot(self, url: str, button_name: str, max_chars: int = 12000) -> str:
        self.calls.append(f"expand:{url}:{button_name}")
        return PAGE_SNAPSHOT


CASE_JSON = {
    "id": "view-posts", "feature_id": "posts", "title": "查看文章", "priority": "P1",
    "steps": [
        {"action": "goto", "url": "http://localhost:8090/login"},
        {"action": "fill", "selector": "label=用户名", "value": "{{ADMIN_USER}}"},
        {"action": "fill", "selector": "label=密码", "value": "{{ADMIN_PASSWORD}}"},
        {"action": "click", "selector": 'role=button[name="登录"]'},
        {"action": "goto", "url": "http://localhost:8090/console/posts"},
        {"action": "wait_for", "text": "文章"},
    ],
    "expected": ["文章列表可见"],
}

SELECT_JSON = {
    "url": "http://localhost:8090/console/posts",
    "reason": "文章列表页",
    "expand_click": None,
}


def test_grounded_two_step_prompts_carry_snapshot_and_site_map():
    llm = FakeLLM([dict(SELECT_JSON), dict(CASE_JSON)])
    grounding: dict = {}
    case = plan_case(llm, feature_desc="查看文章列表", feature_id="posts",
                     explorer=FakeExplorer(), grounding=grounding)
    assert case.id == "view-posts"
    phases = [c["phase"] for c in llm.calls]
    assert phases[0] == "plan:grounded:select:r1"
    assert phases[1] == "plan:grounded:write:r1"
    assert "站点地图" in llm.calls[0]["user"]
    assert "console/posts" in llm.calls[0]["user"]
    assert "请输入标题" in llm.calls[1]["system"]  # 快照进了写用例提示词
    assert grounding["status"] == "ok" and grounding["page_url"] == SELECT_JSON["url"]
    assert grounding["mode"] == "grounded"


def test_grounded_selector_violation_repaired_once():
    from agent.schema import Case
    bad_case = dict(CASE_JSON, steps=[
        {"action": "click", "selector": 'role=button[name="保存"]'},  # 子串违例
    ])
    llm = FakeLLM([dict(SELECT_JSON), bad_case, dict(CASE_JSON)])
    grounding: dict = {}
    case = plan_case(llm, feature_desc="x", feature_id="posts",
                     explorer=FakeExplorer(), grounding=grounding)
    assert [c["phase"] for c in llm.calls][-1] == "plan:grounded:repair"
    # 修复轮提示词里带了具体违例
    assert "保存" in llm.calls[-1]["user"]
    assert "violations" not in grounding  # 修复后通过
    assert isinstance(case, Case)


def test_grounded_unrepaired_violations_recorded():
    bad_case = dict(CASE_JSON, steps=[
        {"action": "click", "selector": 'role=button[name="保存"]'},
    ])
    llm = FakeLLM([dict(SELECT_JSON), bad_case, bad_case])
    grounding: dict = {}
    plan_case(llm, feature_desc="x", feature_id="posts",
              explorer=FakeExplorer(), grounding=grounding)
    assert grounding.get("violations") and "保存" in grounding["violations"][0]


def test_grounded_select_page_must_come_from_site_map():
    off_map = {"url": "http://localhost:8090/console/roles", "reason": "猜的", "expand_click": None}
    llm = FakeLLM([off_map, dict(SELECT_JSON), dict(CASE_JSON)])
    grounding: dict = {}
    plan_case(llm, feature_desc="x", feature_id="posts",
              explorer=FakeExplorer(), grounding=grounding)
    # 第一轮选了不在站点地图的 URL → 错误回传重选
    assert "不在站点地图" in llm.calls[1]["user"]
    assert grounding["page_url"] == SELECT_JSON["url"]


def test_explorer_failure_falls_back_to_baseline():
    llm = FakeLLM([dict(CASE_JSON)])
    grounding: dict = {}
    ex = FakeExplorer(fail=RuntimeError("登录失败"))
    case = plan_case(llm, feature_desc="x", feature_id="posts",
                     explorer=ex, grounding=grounding)
    assert case.id == "view-posts"
    assert grounding["status"] == "fallback" and grounding["mode"] == "baseline"
    assert "登录失败" in grounding["reason"]
    assert llm.calls[0]["phase"].startswith("plan:r")  # 降级走 baseline 提示词


def test_grounded_without_explorer_is_explicit_fallback():
    llm = FakeLLM([dict(CASE_JSON)])
    grounding: dict = {}
    plan_case(llm, feature_desc="x", feature_id="posts", grounding=grounding)
    assert grounding["status"] == "fallback" and "explorer" in grounding["reason"]


def test_baseline_mode_keeps_old_prompt():
    llm = FakeLLM([dict(CASE_JSON)])
    grounding: dict = {}
    plan_case(llm, feature_desc="x", feature_id="posts", mode="baseline",
              grounding=grounding)
    assert grounding["mode"] == "baseline" and grounding["status"] == "n/a"
    assert "文章编辑器" in llm.calls[0]["system"]  # baseline 保留页面具体事实
    assert [c["phase"] for c in llm.calls] == ["plan:r1"]


def test_grounded_max_rounds_gives_up():
    llm = FakeLLM([dict(SELECT_JSON), {"id": "x"}, {"id": "x"}])
    with pytest.raises(PlannerError):
        plan_case(llm, feature_desc="x", feature_id="posts", explorer=FakeExplorer())
