"""Tests for the gateway interfaces, the D0 defense and the registry."""

from __future__ import annotations

import pytest

from agentbank_gateway import (
    Allow,
    AskHuman,
    Defense,
    Deny,
    Message,
    NoDefense,
    RunContext,
    TaggedValue,
    ToolCall,
    available,
    get_defense,
    register_defense,
)


def test_nodefense_satisfies_protocol() -> None:
    assert isinstance(NoDefense(), Defense)


def test_nodefense_is_passthrough() -> None:
    d = NoDefense()
    ctx = RunContext(run_id="r1")
    messages = [Message(role="user", content="hi")]
    assert d.on_llm_input(messages, ctx) == messages
    tagged = TaggedValue(value="x", provenance="test", trust="untrusted")
    assert d.on_tool_output("get_accounts", tagged, ctx) == tagged
    assert isinstance(d.on_tool_call(ToolCall(name="transfer"), ctx), Allow)
    assert d.on_final("done", ctx) == "done"


def test_decision_types() -> None:
    assert Deny(reason="blocked").reason == "blocked"
    assert AskHuman(prompt="approve?").prompt == "approve?"


def test_tagged_value_defaults_to_untrusted() -> None:
    assert TaggedValue(value="v", provenance="p").trust == "untrusted"


def test_registry_has_d0() -> None:
    assert "D0" in available()
    assert isinstance(get_defense("D0"), NoDefense)


def test_registry_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_defense("D-does-not-exist")


def test_register_and_resolve() -> None:
    register_defense("D-test", NoDefense)
    assert "D-test" in available()
    assert isinstance(get_defense("D-test"), Defense)
