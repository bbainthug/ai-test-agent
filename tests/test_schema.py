import pytest
from pydantic import ValidationError

from agent.schema import Case, Step


def _case(**over):
    base = {
        "id": "login-admin",
        "title": "登录",
        "priority": "P0",
        "steps": [{"action": "goto", "url": "{{BASE_URL}}/login"}],
        "expected": ["进入控制台"],
    }
    base.update(over)
    return base


def test_valid_case_roundtrip():
    c = Case.model_validate(_case())
    assert c.steps[0].params() == {"url": "{{BASE_URL}}/login"}


@pytest.mark.parametrize(
    "step",
    [
        {"action": "goto"},
        {"action": "click"},
        {"action": "fill", "selector": "label=用户名"},
        {"action": "select", "value": "x"},
        {"action": "wait_for"},
        {"action": "assert_text"},
        {"action": "assert_visible"},
        {"action": "assert_url"},
    ],
)
def test_each_action_requires_its_params(step):
    with pytest.raises(ValidationError):
        Step.model_validate(step)


def test_unknown_action_rejected():
    with pytest.raises(ValidationError):
        Step.model_validate({"action": "evaluate_js", "value": "alert(1)"})


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        Step.model_validate({"action": "goto", "url": "/", "script": "x"})


def test_only_whitelisted_template_vars():
    Step.model_validate({"action": "fill", "selector": "label=密码", "value": "{{ADMIN_PASSWORD}}"})
    with pytest.raises(ValidationError):
        Step.model_validate({"action": "fill", "selector": "label=密码", "value": "{{DB_PASSWORD}}"})


@pytest.mark.parametrize(
    "over",
    [
        {"id": "Bad ID"},
        {"title": "   "},
        {"steps": []},
        {"expected": ["", "  "]},
        {"priority": "P9"},
    ],
)
def test_case_level_validation(over):
    with pytest.raises(ValidationError):
        Case.model_validate(_case(**over))
