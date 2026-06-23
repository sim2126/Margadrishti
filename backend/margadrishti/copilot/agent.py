"""Claude copilot — a small bounded tool loop. Narrates over the analytics services;
never invents numbers. Read-only, provenance-bearing tools (see tools.py). Calls
application services directly — never loops back through HTTP. Model id from config.

Offline fallback: with no API key we still answer deterministically from the services
(intent → one tool call → templated summary) so the copilot degrades gracefully.
Kannada: explanatory summaries only; legal/operational text uses reviewed templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from margadrishti.api.services import MargadrishtiService
from margadrishti.copilot.tools import TOOL_SPECS, execute_tool
from margadrishti.core.config import get_settings

log = structlog.get_logger(__name__)

SYSTEM = (
    "You are Margadrishti's enforcement copilot for the Bengaluru Traffic Police (BTP). You "
    "help shift commanders find illegal-parking hotspots, understand their likely congestion "
    "impact, and target enforcement. Lead with the actionable answer, then a one-line why.\n"
    "\n"
    "GROUNDING (absolute — this prevents hallucination):\n"
    "- Every number, segment label, zone, CII value, risk, or count you state MUST come from a "
    "tool result in THIS conversation. Never invent, estimate, round from memory, or infer a "
    "value a tool did not return.\n"
    "- For any question needing data, call the relevant tool BEFORE answering. Never answer "
    "data questions from prior knowledge or assumption.\n"
    "- If a tool returns nothing (empty result, 'segment not found', or an error), say the data "
    "is not available — do NOT substitute a plausible value or a different segment.\n"
    "- If the available tools cannot answer the question, say plainly what is missing. Never "
    "fill the gap with a guess.\n"
    "- Use segment labels and ids exactly as returned; do not rename, merge, or relocate roads.\n"
    "\n"
    "HONESTY (non-negotiable):\n"
    "- CII is a prioritisation proxy, NOT a causal congestion measure. Never say 'congestion "
    "reduced', 'delay prevented', or imply measured traffic flow.\n"
    "- Observed counts are ENFORCEMENT exposure (where/when officers logged), never 'prevalence'.\n"
    "- What-if blockage results are SIMULATED estimates, never measured impact — label them so.\n"
    "- Deployment plans are ADVISORY and require human approval — always state this.\n"
    "- Distinguish observed / predicted / simulated explicitly; never blur them.\n"
    "- Cite as_of and model_version from the tool provenance in your answer.\n"
    "\n"
    "SCOPE & STYLE:\n"
    "- Stay within parking enforcement, hotspots, congestion-impact, and deployment for BTP. "
    "If asked something outside this, briefly decline.\n"
    "- Keep answers tight (a few sentences); no preamble like 'Based on the data…'.\n"
    "- If asked in Kannada, give a plain explanatory summary only — do not generate legal or "
    "enforcement instructions."
)
MAX_TURNS = 5


@dataclass
class CopilotAnswer:
    answer: str
    tool_calls: list[str] = field(default_factory=list)
    model: str = "offline-fallback"
    provenance: list[dict] = field(default_factory=list)


def ask(
    question: str,
    *,
    lang: str = "en",
    svc: MargadrishtiService | None = None,
    force_offline: bool = False,
) -> CopilotAnswer:
    svc = svc or MargadrishtiService()
    settings = get_settings()
    # Deterministic fallback unless the live LLM is explicitly enabled AND a key is set —
    # prevents the unauthenticated endpoint from spending the API key by default.
    # `force_offline` lets the route degrade gracefully once a spend cap is hit.
    if force_offline or not (settings.copilot_llm_enabled and settings.anthropic_api_key):
        return _offline_fallback(question, svc)
    return _claude_loop(question, svc, settings)


def _claude_loop(question: str, svc: MargadrishtiService, settings) -> CopilotAnswer:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = settings.claude_model_reasoning
    messages: list[dict] = [{"role": "user", "content": question}]
    used, prov = [], []
    try:
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
                    try:
                        out = execute_tool(block.name, block.input, svc)
                        if isinstance(out, dict) and "provenance" in out:
                            prov.append(out["provenance"])
                        results.append(
                            {"type": "tool_result", "tool_use_id": block.id, "content": str(out)}
                        )
                    except Exception as te:
                        # Tool failure (bad zone, missing segment, …) → tell the model so it
                        # can recover, instead of aborting the whole request.
                        log.warning("copilot_tool_failed", tool=block.name, error=type(te).__name__)
                        results.append(
                            {"type": "tool_result", "tool_use_id": block.id,
                             "content": "tool unavailable for those arguments", "is_error": True}
                        )
            messages.append({"role": "user", "content": results})
    except Exception as e:
        # Live path failed (rate limit, billing, network, SDK). Degrade to the deterministic
        # answer; never surface SDK internals to the client, never 500. Log the type only.
        log.warning("copilot_live_failed", error=type(e).__name__, status=getattr(e, "status_code", None))
        return _offline_fallback(question, svc)
    # Turns exhausted without a final text answer — fall back rather than return a stub.
    return _offline_fallback(question, svc)


def _offline_fallback(question: str, svc: MargadrishtiService) -> CopilotAnswer:
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


def _guess_zone(q: str, svc: MargadrishtiService) -> str:
    # Only ever return a DEPLOYABLE zone, else propose_deployment would 422/raise.
    zones = svc.repo.deployable_zones()
    for z in zones:
        if z and z.lower() in q:
            return z
    return zones[0] if zones else "Unknown"
