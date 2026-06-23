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


def test_api_key_never_enters_model_context_or_response(monkeypatch):
    """Key-exposure guard: the API key authenticates the SDK client ONLY. It must never
    appear in system/tools/messages (so prompt injection can't exfiltrate it) or in the
    response. svc=object() — the immediate end_turn means no tool runs, so no gold needed."""
    SECRET = "SECRET-KEY-DO-NOT-LEAK"
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("MARGA_COPILOT_LLM_ENABLED", "true")
    get_settings.cache_clear()

    seen: dict = {}

    class FakeMessages:
        def create(self, **kw):
            seen.update(kw)
            return types.SimpleNamespace(
                stop_reason="end_turn",
                content=[types.SimpleNamespace(type="text", text="Top spot A Rd. as_of=2024-04-08.")],
            )

    class FakeClient:
        def __init__(self, **kw):
            self.messages = FakeMessages()

    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)

    ans = agent.ask("Where should I focus enforcement?", svc=object())
    context_blob = repr(seen.get("system")) + repr(seen.get("tools")) + repr(seen.get("messages"))
    assert SECRET not in context_blob          # never sent into the model context
    assert SECRET not in (ans.answer + repr(ans.tool_calls) + ans.model)


@requires_gold
def test_live_failure_degrades_to_offline(monkeypatch):
    """A failing SDK call (rate limit / billing / network) must degrade to the deterministic
    answer — never a 500, never SDK internals to the client."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("MARGA_COPILOT_LLM_ENABLED", "true")
    get_settings.cache_clear()

    class FakeMessages:
        def create(self, **kw):
            raise RuntimeError("simulated upstream failure")

    class FakeClient:
        def __init__(self, **kw):
            self.messages = FakeMessages()

    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)

    ans = agent.ask("top congestion impact spots")
    assert ans.model == "offline-fallback"
    assert ans.answer


@requires_gold
def test_offline_fallback_answers_with_provenance(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")   # override any key in backend/.env
    get_settings.cache_clear()
    ans = agent.ask("Show me the top congestion impact spots")
    assert ans.model == "offline-fallback"
    assert ans.answer and ans.provenance


def test_limiter_caps_session_then_day():
    from margadrishti.copilot.limiter import CopilotLimiter

    lim = CopilotLimiter(max_per_session=2, max_per_day=3)
    assert lim.try_consume("s1") == (True, None)
    assert lim.try_consume("s1") == (True, None)
    assert lim.try_consume("s1") == (False, "session")   # per-session cap, consumes nothing
    assert lim.try_consume("s2") == (True, None)          # fresh session still allowed
    assert lim.try_consume("s3") == (False, "day")        # global daily ceiling reached


@requires_gold
def test_ask_force_offline_skips_live(monkeypatch):
    """Even with the live path enabled, force_offline degrades to the deterministic answer
    (no network) — this is the path the route takes once a spend cap is hit."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("MARGA_COPILOT_LLM_ENABLED", "true")
    get_settings.cache_clear()
    ans = agent.ask("top congestion impact spots", force_offline=True)
    assert ans.model == "offline-fallback"
    assert ans.answer


@requires_gold
def test_copilot_route_carries_mode_and_notice(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")   # override any key in backend/.env
    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from margadrishti.api.app import app

    r = TestClient(app).post("/copilot/ask", json={"question": "top congestion impact spots"})
    assert r.status_code == 200
    b = r.json()
    assert b["mode"] == "fallback"          # no key configured → deterministic answer
    assert b["notice"] is None              # caps only apply on the live path
    assert b["answer"]


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
