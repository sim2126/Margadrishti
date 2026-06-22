"""Claude copilot — a small bounded tool loop. Narrates over the analytics services;
never invents numbers. Read-only, provenance-bearing tools (see tools.py). Calls
application services directly — never loops back through HTTP. Model id from config.

Offline fallback: with no API key we still answer deterministically from the services
(intent → one tool call → templated summary) so the copilot degrades gracefully.
Kannada: explanatory summaries only; legal/operational text uses reviewed templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from parkiq.api.services import ParkIQService
from parkiq.copilot.tools import TOOL_SPECS, execute_tool
from parkiq.core.config import get_settings

SYSTEM = (
    "You are ParkIQ's enforcement copilot for the Bengaluru Traffic Police. Answer ONLY "
    "from tool results — never invent numbers. Always cite as_of and model_version from "
    "provenance. CII is a prioritisation proxy, not a causal congestion measure; never say "
    "'congestion reduced' or 'delay prevented'. Deployment plans are advisory and require "
    "human approval. If asked in Kannada, give an explanatory summary only."
)
MAX_TURNS = 5


@dataclass
class CopilotAnswer:
    answer: str
    tool_calls: list[str] = field(default_factory=list)
    model: str = "offline-fallback"
    provenance: list[dict] = field(default_factory=list)


def ask(question: str, *, lang: str = "en", svc: ParkIQService | None = None) -> CopilotAnswer:
    svc = svc or ParkIQService()
    settings = get_settings()
    # Deterministic fallback unless the live LLM is explicitly enabled AND a key is set —
    # prevents the unauthenticated endpoint from spending the API key by default.
    if not (settings.copilot_llm_enabled and settings.anthropic_api_key):
        return _offline_fallback(question, svc)
    return _claude_loop(question, svc, settings)


def _claude_loop(question: str, svc: ParkIQService, settings) -> CopilotAnswer:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = settings.claude_model_reasoning
    messages: list[dict] = [{"role": "user", "content": question}]
    used, prov = [], []
    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=model, max_tokens=1024, system=SYSTEM, tools=TOOL_SPECS, messages=messages
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return CopilotAnswer(answer=text, tool_calls=used, model=model, provenance=prov)
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                used.append(block.name)
                out = execute_tool(block.name, block.input, svc)
                if "provenance" in out:
                    prov.append(out["provenance"])
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(out)}
                )
        messages.append({"role": "user", "content": results})
    return CopilotAnswer(answer="(stopped: max turns)", tool_calls=used, model=model, provenance=prov)


def _offline_fallback(question: str, svc: ParkIQService) -> CopilotAnswer:
    """Deterministic intent routing so the copilot works with no API key."""
    q = question.lower()
    if any(w in q for w in ("deploy", "patrol", "units", "officer", "send")):
        out = execute_tool("propose_deployment", {"zone": _guess_zone(q, svc), "n_units": 3}, svc)
        n = len(out["routes"])
        ans = (f"Advisory plan for {out['zone']}: {n} unit route(s), priority utility "
               f"{out['total_priority_utility']} (solver={out['solver']}). "
               f"Requires human approval. {out['method_caveats']} "
               f"as_of={out['provenance']['as_of']}.")
        return CopilotAnswer(answer=ans, tool_calls=["propose_deployment"], provenance=[out["provenance"]])
    if "forecast" in q or "predict" in q or "tomorrow" in q:
        out = execute_tool("get_forecast", {"limit": 5}, svc)
        top = ", ".join(f"{i['label']} (risk {i['risk']})" for i in out["items"][:5])
        return CopilotAnswer(answer=f"Top predicted-risk segments: {top}. as_of={out['provenance']['as_of']}.",
                             tool_calls=["get_forecast"], provenance=[out["provenance"]])
    if "trend" in q or "zone" in q or "density" in q:
        out = execute_tool("get_zone_trends", {}, svc)
        top = ", ".join(f"{z['zone']} ({z['observed_count']})" for z in out["zones"][:5])
        return CopilotAnswer(answer=f"Observed enforcement density by zone (not prevalence): {top}.",
                             tool_calls=["get_zone_trends"], provenance=[out["provenance"]])
    out = execute_tool("get_segment_cii", {"limit": 5}, svc)
    top = ", ".join(f"{s['label']} (CII {s['cii']})" for s in out["segments"][:5])
    return CopilotAnswer(answer=f"Top Congestion-Impact segments: {top}. "
                                f"CII is a prioritisation proxy. as_of={out['provenance']['as_of']}.",
                         tool_calls=["get_segment_cii"], provenance=[out["provenance"]])


def _guess_zone(q: str, svc: ParkIQService) -> str:
    # Only ever return a DEPLOYABLE zone, else propose_deployment would 422/raise.
    zones = svc.repo.deployable_zones()
    for z in zones:
        if z and z.lower() in q:
            return z
    return zones[0] if zones else "Unknown"
