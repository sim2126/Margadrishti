"""Copilot: tool restrictions, offline fallback, mocked tool-loop, gated live test."""

from __future__ import annotations

import os
import sys
import types

import pytest

from margadrishti.copilot import agent
from margadrishti.copilot.tools import TOOL_SPECS, execute_tool
from margadrishti.core.config import get_settings
from tests.conftest import requires_gold

ALLOWED_TOOLS = {
    "get_segment_cii", "get_forecast", "get_zone_trends", "propose_deployment",
    "get_road_neighborhood", "simulate_parking_blockage", "get_segment_history",
}


def test_tools_are_read_only_allowlist():
    names = {t["name"] for t in TOOL_SPECS}
    assert names == ALLOWED_TOOLS
    # No tool exposes raw SQL/python/exec affordances.
    for t in TOOL_SPECS:
        assert not any(bad in t["name"] for bad in ("sql", "exec", "python", "shell"))


def test_unknown_tool_rejected():
    with pytest.raises(ValueError):
        execute_tool("delete_everything", {}, svc=object())


def test_mocked_claude_tool_loop(monkeypatch):
    """A fake Anthropic client that issues one tool_use then a final text answer.
    Verifies the loop executes tools and returns the model's text."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("MARGA_COPILOT_LLM_ENABLED", "true")
    get_settings.cache_clear()

    captured = {}

    def fake_execute(name, args, svc):
        captured["tool"] = name
        return {"provenance": {"as_of": "2024-04-08"}, "segments": []}

    monkeypatch.setattr(agent, "execute_tool", fake_execute)

    def block(**kw):
        return types.SimpleNamespace(**kw)

    class FakeMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kw):
            self.calls += 1
            if self.calls == 1:
                return types.SimpleNamespace(
                    stop_reason="tool_use",
                    content=[block(type="tool_use", name="get_segment_cii", input={}, id="t1")],
                )
            return types.SimpleNamespace(
                stop_reason="end_turn",
                content=[block(type="text", text="Top segment is A Rd. as_of=2024-04-08.")],
            )

    class FakeClient:
        def __init__(self, **kw):
            self.messages = FakeMessages()

    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)

    ans = agent.ask("Where are the worst spots?", svc=object())
    assert "A Rd" in ans.answer
    assert captured["tool"] == "get_segment_cii"
    assert "get_segment_cii" in ans.tool_calls
    assert ans.provenance and ans.provenance[0]["as_of"] == "2024-04-08"


@requires_gold
def test_offline_fallback_answers_with_provenance(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    ans = agent.ask("Show me the top congestion impact spots")
    assert ans.model == "offline-fallback"
    assert ans.answer and ans.provenance


@pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("MARGA_LIVE") == "1"),
    reason="live Claude test; set ANTHROPIC_API_KEY and MARGA_LIVE=1",
)
@requires_gold
def test_live_claude_integration(monkeypatch):
    monkeypatch.setenv("MARGA_COPILOT_LLM_ENABLED", "true")
    get_settings.cache_clear()
    ans = agent.ask("Which zone has the highest observed enforcement density?")
    assert ans.model != "offline-fallback"
    assert ans.answer
