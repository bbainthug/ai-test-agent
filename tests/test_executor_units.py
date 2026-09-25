"""执行器里不依赖浏览器的部分：模板渲染、选择器解析、故障与接口记录。"""

import pytest
from conftest import FakeScope

from agent.executor import (
    ExecutionResult,
    Executor,
    Fault,
    StepFailure,
    StepResult,
    _resolve_single,
    render_template,
    resolve_locator,
)


def test_render_template_substitutes_known_vars():
    assert render_template("{{BASE_URL}}/login", {"BASE_URL": "http://h"}) == "http://h/login"


def test_render_template_unknown_var_is_locator_failure():
    with pytest.raises(StepFailure) as e:
        render_template("{{NOPE}}", {})
    assert e.value.failure_class == "locator_failed"


@pytest.mark.parametrize(
    "expr,engine,how",
    [
        ('role=button[name="发布"]', "role", "role"),
        ("role=textbox", "role", "role"),
        ("label=用户名", "label", "label"),
        ("text=发布", "text", "text"),
        ("placeholder=搜索", "placeholder", "placeholder"),
        ("testid=save", "testid", "testid"),
        ("css=.btn", "css", "locator"),
        ("xpath=//a", "xpath", "locator"),
        ("//a", "xpath", "locator"),
        (".plain-css", "css", "locator"),
    ],
)
def test_selector_engines(expr, engine, how):
    loc, eng = _resolve_single(FakeScope(), expr)
    assert eng == engine
    assert loc.path[-1][0] == how


def test_role_name_passed_through():
    loc, _ = _resolve_single(FakeScope(), 'role=button[name="保存"]')
    assert loc.path[-1] == ("role", ("button",), (("name", "保存"),))


def test_chain_selector_scopes_each_part():
    loc, engine = resolve_locator(FakeScope(), 'role=dialog >> role=button[name="发布"]')
    assert engine == "role-chain"
    assert [p[0] for p in loc.path] == ["role", "role"]


def test_failed_step_property():
    r = ExecutionResult(case_id="c", started_at="", finished_at="", final_url="")
    r.steps = [StepResult(1, "goto", {}, "passed"), StepResult(2, "click", {}, "failed")]
    assert r.failed_step.index == 2


def test_record_api_keeps_app_calls_only():
    r = ExecutionResult(case_id="c", started_at="", finished_at="", final_url="")

    class Req:
        def __init__(self, method, url):
            self.method, self.url = method, url

    for req in (
        Req("GET", "http://localhost:8090/apis/api.console.halo.run/v1alpha1/posts?page=1"),
        Req("GET", "http://localhost:8090/apis/api.console.halo.run/v1alpha1/posts?page=2"),
        Req("GET", "http://localhost:8090/console/assets/index.js"),
        Req("PUT", "http://localhost:8090/api/v1alpha1/configmaps/system"),
    ):
        Executor._record_api(r, req)
    assert r.api_calls == {
        "GET /apis/api.console.halo.run/v1alpha1/posts": 2,
        "PUT /api/v1alpha1/configmaps/system": 1,
    }


def test_fault_serialization():
    f = Fault(url_regex=r"/apis/.*/posts", status=503, method="GET")
    assert f.to_dict() == {"url_regex": r"/apis/.*/posts", "status": 503, "method": "GET"}
    r = ExecutionResult(case_id="c", started_at="", finished_at="", final_url="", faults=[f])
    assert r.to_dict()["faults"] == [f.to_dict()]
    assert r.to_dict()["faults_hit"] == 0
