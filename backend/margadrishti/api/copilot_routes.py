"""Copilot HTTP route. Thin: delegates to the copilot agent, which calls the same
application services as the rest of the API (no HTTP loopback).

Spend guard: when the live LLM path is enabled, a per-session + per-day cap gates live
calls (the endpoint is unauthenticated). On exceed, we degrade to the deterministic
offline answer over the same data rather than erroring — the copilot still 'works'.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from margadrishti.copilot.agent import ask
from margadrishti.copilot.limiter import CopilotLimiter
from margadrishti.core.config import get_settings

router = APIRouter(prefix="/copilot", tags=["copilot"])

_settings = get_settings()
_limiter = CopilotLimiter(_settings.copilot_max_per_session, _settings.copilot_max_per_day)

_SESSION_NOTICE = (
    "You've reached this session's live-assistant limit — here's a quick built-in answer "
    "from the same data."
)
_DAY_NOTICE = (
    "The live assistant is at capacity right now — here's a quick built-in answer from the "
    "same data."
)


class CopilotAskRequest(BaseModel):
    question: str
    lang: str = "en"


class CopilotAskResponse(BaseModel):
    answer: str
    tool_calls: list[str]
    model: str
    provenance: list[dict]
    mode: str = "fallback"            # "live" (Claude answered) | "fallback" (deterministic)
    notice: str | None = None         # set when a spend cap forced the fallback


def _session_id(request: Request) -> str:
    sid = request.headers.get("x-session-id")
    if sid:
        return sid[:128]
    return request.client.host if request.client else "anon"


@router.post("/ask", response_model=CopilotAskResponse)
def copilot_ask(req: CopilotAskRequest, request: Request) -> CopilotAskResponse:
    settings = get_settings()
    live_possible = bool(settings.copilot_llm_enabled and settings.anthropic_api_key)

    notice: str | None = None
    if live_possible:
        allowed, reason = _limiter.try_consume(_session_id(request))
        if allowed:
            a = ask(req.question, lang=req.lang)
        else:
            a = ask(req.question, lang=req.lang, force_offline=True)
            notice = _SESSION_NOTICE if reason == "session" else _DAY_NOTICE
    else:
        # Live path not configured — always the deterministic answer; no caps to apply.
        a = ask(req.question, lang=req.lang)

    mode = "live" if a.model != "offline-fallback" else "fallback"
    return CopilotAskResponse(
        answer=a.answer, tool_calls=a.tool_calls, model=a.model,
        provenance=a.provenance, mode=mode, notice=notice,
    )
