"""Copilot tools = thin wrappers over the SAME application services the API uses.
Read-only and provenance-bearing. No SQL/Python execution, no enforcement side effects
(propose_deployment returns an advisory plan that still needs human approval).
"""

from __future__ import annotations

from typing import Any

from margadrishti.api.models import DeploymentPlanRequest
from margadrishti.api.services import MargadrishtiService

# Anthropic tool schemas (kept minimal and bounded — no free-form query tool).
TOOL_SPECS: list[dict] = [
    {
        "name": "get_segment_cii",
        "description": "Top Congestion-Impact-Index segments (optionally filtered to a zone). "
                       "CII is a prioritisation proxy, not a causal congestion measure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
                "zone": {"type": "string"},
            },
        },
    },
    {
        "name": "get_forecast",
        "description": "Top predicted-risk segments for the latest horizon (bias-adjusted).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
                "zone": {"type": "string"},
            },
        },
    },
    {
        "name": "get_zone_trends",
        "description": "Observed enforcement density by zone (NOT true prevalence).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_deployment",
        "description": "Advisory patrol plan for a zone (requires human approval).",
        "input_schema": {
            "type": "object",
            "properties": {
                "zone": {"type": "string"},
                "n_units": {"type": "integer", "default": 3},
                "shift_minutes": {"type": "integer", "default": 240},
            },
            "required": ["zone"],
        },
    },
    {
        "name": "get_road_neighborhood",
        "description": "k-hop road-network neighbours of a segment — where congestion can "
                       "propagate. Use to reason about downstream/adjacent junctions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_id": {"type": "string"},
                "hops": {"type": "integer", "default": 2},
            },
            "required": ["segment_id"],
        },
    },
    {
        "name": "simulate_parking_blockage",
        "description": "What-if: illegal parking blocks lane(s) on a segment for some minutes "
                       "→ MODELLED (not measured) spillover impact on neighbouring segments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_id": {"type": "string"},
                "lanes_blocked": {"type": "integer", "default": 1},
                "minutes": {"type": "integer", "default": 45},
            },
            "required": ["segment_id"],
        },
    },
    {
        "name": "get_segment_history",
        "description": "Hour-of-week observed-enforcement profile for a segment (when it spikes).",
        "input_schema": {
            "type": "object",
            "properties": {"segment_id": {"type": "string"}},
            "required": ["segment_id"],
        },
    },
]


def execute_tool(name: str, args: dict[str, Any], svc: MargadrishtiService) -> dict:
    """Return a JSON-serialisable, provenance-bearing tool result."""
    if name == "get_segment_cii":
        r = svc.cii_map(limit=int(args.get("limit", 10)), zone=args.get("zone"))
        return {
            "segments": [s.model_dump() for s in r.segments[: int(args.get("limit", 10))]],
            "provenance": r.provenance.model_dump(),
        }
    if name == "get_forecast":
        r = svc.forecast(limit=int(args.get("limit", 10)), zone=args.get("zone"))
        return {"items": [i.model_dump() for i in r.items], "provenance": r.provenance.model_dump()}
    if name == "get_zone_trends":
        r = svc.zone_trends()
        return {"zones": [z.model_dump() for z in r.zones], "provenance": r.provenance.model_dump()}
    if name == "propose_deployment":
        r = svc.deployment_plan(
            DeploymentPlanRequest(
                zone=args["zone"], n_units=int(args.get("n_units", 3)),
                shift_minutes=int(args.get("shift_minutes", 240)),
            )
        )
        return r.model_dump()
    if name == "get_road_neighborhood":
        return svc.neighborhood(args["segment_id"], hops=int(args.get("hops", 2)))
    if name == "simulate_parking_blockage":
        res = svc.simulate_blockage(
            args["segment_id"], lanes_blocked=int(args.get("lanes_blocked", 1)),
            minutes=int(args.get("minutes", 45)),
        )
        return res.model_dump() if res else {"error": "segment not found"}
    if name == "get_segment_history":
        return svc.segment_history(args["segment_id"])
    raise ValueError(f"unknown tool {name}")
