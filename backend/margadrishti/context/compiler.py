"""Traffic Context Compiler.

Before the copilot answers, we assemble a typed, evidence-kinded context so the model
never treats a stale enforcement dataset as live traffic. Every section is explicitly
tagged OBSERVED / PREDICTED / SIMULATED, and the things we *don't* have are listed as
MISSING (data_gaps). This is the honesty backbone (CLAUDE.md: distinguish observed facts,
model predictions, simulated estimates, and missing information).
"""

from __future__ import annotations

from pydantic import BaseModel

from margadrishti.api.models import Provenance
from margadrishti.core.versioning import now_rfc3339
from margadrishti.simulate.flow import SimulationResult, k_hop_neighborhood, simulate_parking_blockage

# What this system structurally cannot observe yet — surfaced on every context so claims
# stay honest and reviewers see the boundary.
STRUCTURAL_DATA_GAPS = [
    "No live traffic feed — state is derived from the historical enforcement dataset.",
    "No flow/speed measurement — congestion impact is modelled, not observed.",
    "No weather/events feed integrated.",
    "Travel direction approximate (no vehicle heading in the source).",
    "Patrol-unit availability not integrated.",
]


class Observed(BaseModel):
    kind: str = "observed"
    cii: float | None = None
    observed_count: int | None = None
    approved_count: float | None = None
    approval_rate: float | None = None
    n_officers: int | None = None
    active_hours: int | None = None


class Predicted(BaseModel):
    kind: str = "predicted"
    risk: float | None = None
    model_version: str | None = None
    note: str = "Bias-adjusted predicted risk; ranking signal, not a flow measurement."


class NeighborSeg(BaseModel):
    physical_id: str
    name: str | None = None
    hop: int


class Neighborhood(BaseModel):
    kind: str = "observed"  # graph structure is observed; congestion on it is not
    hops: int
    segments: list[NeighborSeg]


class Uncertainty(BaseModel):
    cii_risk_is_interim_biased: bool = False
    learned_model_shipped: bool = False  # did LightGBM beat both gates? else baseline
    mean_match_confidence: float | None = None


class TrafficContext(BaseModel):
    as_of: str
    generated_at: str
    focus: dict
    horizon_minutes: int
    observed: Observed
    predicted: Predicted
    neighborhood: Neighborhood
    simulation: SimulationResult | None = None
    uncertainty: Uncertainty
    data_gaps: list[str]
    provenance: Provenance


def _provenance(repo) -> Provenance:
    m = repo.manifest()
    etl, model = m.get("etl", {}), m.get("model", {})
    return Provenance(
        generated_at=now_rfc3339(),
        as_of=str(model.get("as_of", etl.get("etl_finished_at", "unknown"))),
        dataset_version=str(etl.get("dataset_version", "unknown")),
        feature_version=str(etl.get("feature_version", "unknown")),
        road_network_version=str(etl.get("road_network_version", "unknown")),
        cii_version=str(etl.get("cii_version", "unknown")),
        model_version=str(model.get("model_version", "unknown")),
        note="CII is a prioritisation proxy; flow impact is simulated, not measured.",
    )


def build_segment_context(
    repo,
    segment_id: str,
    *,
    horizon_minutes: int = 60,
    run_simulation: bool = False,
    lanes_blocked: int = 1,
    minutes: int = 45,
    hops: int = 2,
) -> TrafficContext | None:
    """Compile the typed context for one segment. `repo` is any repository implementing
    segment_detail / all_segments / manifest (gold or PostGIS)."""
    d = repo.segment_detail(segment_id)
    if d is None:
        return None
    segs = repo.all_segments()

    nbrs = k_hop_neighborhood(segment_id, segs, hops)
    names = segs.set_index("physical_id")["name"].to_dict()
    neighborhood = Neighborhood(
        hops=hops,
        segments=[NeighborSeg(physical_id=p, name=names.get(p), hop=h) for p, h in nbrs[:50]],
    )

    sim = (
        simulate_parking_blockage(segment_id, segs, lanes_blocked=lanes_blocked, minutes=minutes, hops=hops)
        if run_simulation
        else None
    )

    interim = bool(d.get("cii_risk_is_interim_biased", False))
    m = repo.manifest().get("model", {})
    gaps = list(STRUCTURAL_DATA_GAPS)
    if d.get("predicted_risk") is None:
        gaps.append("No model prediction for this segment (insufficient history).")

    def _f(v):
        return None if v is None else float(v)

    return TrafficContext(
        as_of=str(m.get("as_of", "unknown")),
        generated_at=now_rfc3339(),
        focus={"type": "segment", "id": segment_id, "name": d.get("name"), "zone": d.get("zone")},
        horizon_minutes=horizon_minutes,
        observed=Observed(
            cii=_f(d.get("cii")),
            observed_count=int(d.get("observed_count") or 0),
            approved_count=_f(d.get("approved_count")),
            approval_rate=_f(d.get("approval_rate")),
            n_officers=int(d.get("n_officers") or 0),
            active_hours=int(d.get("active_hours") or 0),
        ),
        predicted=Predicted(risk=_f(d.get("predicted_risk")), model_version=str(m.get("model_version", "unknown"))),
        neighborhood=neighborhood,
        simulation=sim,
        uncertainty=Uncertainty(
            cii_risk_is_interim_biased=interim,
            learned_model_shipped=bool(m.get("lightgbm_ships", False)),
            mean_match_confidence=_f(d.get("mean_match_confidence")),
        ),
        data_gaps=gaps,
        provenance=_provenance(repo),
    )
