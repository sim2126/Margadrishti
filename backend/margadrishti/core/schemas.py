"""Canonical typed records. The PII boundary is enforced here.

The raw violations CSV mixes operational fields with personally identifying ones
(vehicle numbers, officer/device ids). At ingestion we split into:
  - `ViolationRecord`   — analytics-safe, flows everywhere downstream.
  - `RestrictedRecord`  — PII, written only to the access-controlled restricted store.
Nothing downstream of ingestion may import or join RestrictedRecord into analytics.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ValidationStatus(StrEnum):
    APPROVED = "approved"        # 115,400 — primary supervised positives
    # 49,754 — NOT an automatic hard negative: with no rejection reason this may be a
    # duplicate, OCR failure, or procedural rejection, not "no violation here". Treat as
    # weak/ambiguous unless a reason field disambiguates it.
    REJECTED = "rejected"
    UNVALIDATED = "unvalidated"  # ~133K (~45%) — confidence-weighted / semi-supervised only


class ViolationRecord(BaseModel):
    """Analytics-safe parking-violation observation (NO PII)."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    lat: float
    lon: float
    location_text: str | None
    violation_types: tuple[str, ...]      # multi-label array from source
    offence_codes: tuple[int, ...]
    observed_at_utc: datetime             # stored UTC; IST features derived in timeutils
    police_station: str | None
    junction_name: str | None
    center_code: str | None
    validation_status: ValidationStatus
    # Bias controls (CLAUDE.md: observed enforcement ≠ prevalence).
    device_ref: str | None = None         # pseudonymous device handle (not the raw id)
    officer_ref: str | None = None        # pseudonymous officer handle (not the raw id)


class RestrictedRecord(BaseModel):
    """PII — restricted store only. Never joined into analytics/UI/LLM context."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    vehicle_number: str | None
    updated_vehicle_number: str | None
    vehicle_type: str | None
    raw_device_id: str | None
    raw_officer_id: str | None


class RoadSegment(BaseModel):
    """Canonical *physical* road segment — the modelling entity. The source data has no
    vehicle heading, so we do not invent a direction: a physical segment carries the
    candidate directed OSM edges that realise it. Parallel roads stay distinct because
    they are distinct physical segments; opposite carriageways of one road collapse to
    one physical segment with two candidate directed edges. H3 cells are render-only."""

    model_config = ConfigDict(frozen=True)

    physical_id: str                      # canonical undirected key: f"{min(u,v)}_{max(u,v)}_{key}"
    directed_edges: tuple[str, ...]       # candidate directed edges "u_v_key" (1 = oneway, 2 = twoway)
    name: str | None
    highway: str | None
    length_m: float
    betweenness: float | None = None      # network centrality (impact weighting)
    h3_cells: tuple[str, ...] = ()        # aggregation/render only


class PointMatch(BaseModel):
    """Result of map-matching one observation. We record confidence, not certainty."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    physical_id: str
    nearest_directed_edge: str            # geometrically nearest candidate (not "the" direction)
    dist_m: float
    match_confidence: float               # 0..1 from distance + nearest/runner-up margin
