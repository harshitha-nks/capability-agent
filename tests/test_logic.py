"""
Fast, browser-free checks for the parts of the system that don't require a
live page: schema round-tripping, guardrail policy enforcement, and
{{param}} substitution. Run with: python -m tests.test_logic
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.schema import Artifact, Step, Locator, InputParam, OutputField, Checkpoint, KnownOutcome
from agent.guardrails import Policy, SafetyViolation
from agent.replay import substitute


def test_artifact_roundtrip():
    artifact = Artifact(
        name="add item to cart and reach checkout overview",
        goal="Log in, add the backpack to the cart, reach checkout overview",
        start_url="https://www.saucedemo.com",
        input_params=[
            InputParam(name="username", secret=True),
            InputParam(name="password", secret=True),
            InputParam(name="item_name"),
        ],
        steps=[
            Step(action="goto", url="https://www.saucedemo.com", description="open"),
            Step(action="type", locator=Locator(strategy="data-test", value="username"),
                 value="{{username}}", description="fill username"),
            Step(action="click", locator=Locator(strategy="data-test", value="login-button",
                 fallbacks=[Locator(strategy="text", value="Login")]),
                 description="submit login"),
        ],
        outputs=[
            OutputField(name="cart_count", locator=Locator(strategy="css", value=".shopping_cart_badge")),
        ],
        checkpoint=Checkpoint(description="reached overview", url_contains="checkout-step-two"),
        known_outcomes=[
            KnownOutcome(name="invalid_login", description="bad credentials",
                         locator=Locator(strategy="data-test", value="error")),
        ],
    )
    raw = artifact.model_dump_json()
    reloaded = Artifact.model_validate_json(raw)
    assert reloaded.steps[2].locator.fallbacks[0].value == "Login"
    assert reloaded.checkpoint.url_contains == "checkout-step-two"
    print("test_artifact_roundtrip: OK")


def test_guardrails():
    policy = Policy(path=os.path.join(os.path.dirname(__file__), "..", "config", "policy.json"))
    policy.check_domain("https://www.saucedemo.com/checkout-step-two.html")
    try:
        policy.check_domain("https://evil.example.com")
        raise AssertionError("expected SafetyViolation for disallowed domain")
    except SafetyViolation:
        pass
    policy.check_action("click")
    try:
        policy.check_action("delete_account")
        raise AssertionError("expected SafetyViolation for disallowed action")
    except SafetyViolation:
        pass
    assert policy.is_risky("Finish") is True
    assert policy.is_risky("Add to cart") is False
    print("test_guardrails: OK")


def test_substitution():
    params = {"username": "standard_user", "password": "secret_sauce"}
    assert substitute("{{username}}", params) == "standard_user"
    assert substitute("no placeholder here", params) == "no placeholder here"
    assert substitute(None, params) is None
    print("test_substitution: OK")


if __name__ == "__main__":
    test_artifact_roundtrip()
    test_guardrails()
    test_substitution()
    print("ALL LOGIC TESTS PASSED")
