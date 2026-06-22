"""Copilot HTTP route. Thin: delegates to the copilot agent, which calls the same
application services as the rest of the API (no HTTP loopback)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from margadrishti.copilot.agent import ask

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotAskRequest(BaseModel):
    question: str
    lang: str = "en"


class CopilotAskResponse(BaseModel):
    answer: str
    tool_calls: list[str]
    model: str
    provenance: list[dict]


@router.post("/ask", response_model=CopilotAskResponse)
def copilot_ask(req: CopilotAskRequest) -> CopilotAskResponse:
    a = ask(req.question, lang=req.lang)
    return CopilotAskResponse(
        answer=a.answer, tool_calls=a.tool_calls, model=a.model, provenance=a.provenance
    )
