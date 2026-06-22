"""Application service layer — the single source of business logic. API routes AND the
copilot call THESE methods (never loop back through HTTP). Each method composes the
read-only repository (and the pure optimiser) and attaches full provenance.
"""

from __future__ import annotations

import hashlib
import math

import pandas as pd

from margadrishti.api.models import (
    CiiMapResponse,
    CiiSegment,
    DeploymentPlanRequest,
    DeploymentPlanResponse,
    ForecastItem,
    ForecastResponse,
    Provenance,
    RouteModel,
    RouteStop,
    SegmentDetail,
    TrendsResponse,
    ZoneTrend,
)
from margadrishti.api.repository import GoldRepository
from margadrishti.context.compiler import TrafficContext, build_segment_context
from margadrishti.core.versioning import now_rfc3339
from margadrishti.optimize.deployment import Stop, optimise_routes
from margadrishti.simulate.flow import SimulationResult, k_hop_neighborhood, simulate_parking_blockage

_CII_NOTE = "CII is a prioritisation proxy, not a causal congestion measure."


class UnknownZoneError(ValueError):
    """Raised when a request names a zone that is not in the served data."""

    def __init__(self, zone: str, valid: list[str]) -> None:
        self.zone = zone
        self.valid = valid
        super().__init__(f"unknown zone {zone!r}")


def _clean(v, default=0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    return v.item() if hasattr(v, "item") else v


def _label(name, junction, zone, physical_id: str) -> str:
    """Operationally distinguishable label so several segments on one road don't all
    read as just 'Hosur Road'. Stable short code disambiguates same name + place."""
    base = (name or "Unnamed road").strip()
    place = (junction or zone or "").strip()
    code = hashlib.sha1(physical_id.encode()).hexdigest()[:4].upper()
    return f"{base} · {place} · {code}" if place else f"{base} · {code}"


class MargadrishtiService:
    def __init__(self, repo: GoldRepository | None = None) -> None:
        self.repo = repo or GoldRepository()

    def _provenance(self, interim_biased: bool | None = None) -> Provenance:
        m = self.repo.manifest()
        etl, model = m.get("etl", {}), m.get("model", {})
        return Provenance(
            generated_at=now_rfc3339(),
            as_of=str(model.get("as_of", etl.get("etl_finished_at", "unknown"))),
            dataset_version=str(etl.get("dataset_version", "unknown")),
            feature_version=str(etl.get("feature_version", "unknown")),
            road_network_version=str(etl.get("road_network_version", "unknown")),
            cii_version=str(etl.get("cii_version", "unknown")),
            model_version=str(model.get("model_version", "unknown")),
            cii_risk_is_interim_biased=bool(interim_biased) if interim_biased is not None else False,
            note=_CII_NOTE,
        )

    def cii_map(self, limit: int = 2000, zone: str | None = None) -> CiiMapResponse:
        df = self.repo.cii_segments(limit=limit, zone=zone)
        interim = bool(df["cii_risk_is_interim_biased"].iloc[0]) if len(df) else False
        segs = [
            CiiSegment(
                physical_id=r.physical_id, name=r.name,
                label=_label(r.name, r.junction, r.zone, r.physical_id),
                junction=r.junction, highway=r.highway, zone=r.zone,
                cii=round(float(r.cii), 4), observed_count=int(r.observed_count),
                approval_rate=_clean(r.approval_rate, None),
                centroid_lat=float(r.centroid_lat), centroid_lon=float(r.centroid_lon),
                component_risk=round(float(r.cii_component__risk), 4),
                component_centrality=round(float(r.cii_component__centrality), 4),
                component_obstruction=round(float(r.cii_component__obstruction), 4),
            )
            for r in df.itertuples()
        ]
        return CiiMapResponse(segments=segs, provenance=self._provenance(interim))

    def segment_detail(self, physical_id: str) -> SegmentDetail | None:
        d = self.repo.segment_detail(physical_id)
        if d is None:
            return None
        why = {
            "predicted_risk": round(float(_clean(d.get("cii_component__risk"))), 4),
            "centrality": round(float(_clean(d.get("cii_component__centrality"))), 4),
            "obstruction": round(float(_clean(d.get("cii_component__obstruction"))), 4),
        }
        return SegmentDetail(
            physical_id=physical_id, name=d.get("name"),
            label=_label(d.get("name"), d.get("junction"), d.get("zone"), physical_id),
            junction=d.get("junction"), zone=d.get("zone"),
            cii=round(float(_clean(d.get("cii"))), 4),
            predicted_risk=_clean(d.get("predicted_risk"), None),
            observed_count=int(_clean(d.get("observed_count"))),
            approved_count=_clean(d.get("approved_count"), None),
            approval_rate=_clean(d.get("approval_rate"), None),
            n_officers=int(_clean(d.get("n_officers"))),
            active_hours=int(_clean(d.get("active_hours"))),
            why=why,
            provenance=self._provenance(bool(d.get("cii_risk_is_interim_biased", False))),
        )

    def forecast(self, limit: int = 50, zone: str | None = None) -> ForecastResponse:
        df = self.repo.forecast(limit=limit, zone=zone)
        items = [
            ForecastItem(
                physical_id=r.physical_id, name=r.name,
                label=_label(r.name, r.junction, r.zone, r.physical_id),
                junction=r.junction, zone=r.zone,
                risk=round(float(_clean(r.risk)), 4), cii=_clean(r.cii, None),
                centroid_lat=float(r.centroid_lat), centroid_lon=float(r.centroid_lon),
            )
            for r in df.itertuples()
        ]
        return ForecastResponse(items=items, provenance=self._provenance())

    def zone_trends(self) -> TrendsResponse:
        df = self.repo.zone_trends()
        zones = [
            ZoneTrend(
                zone=r.zone, n_segments=int(r.n_segments),
                observed_count=int(_clean(r.observed_count)),
                mean_cii=round(float(_clean(r.mean_cii)), 4),
            )
            for r in df.itertuples()
        ]
        return TrendsResponse(zones=zones, provenance=self._provenance())

    def deployment_plan(self, req: DeploymentPlanRequest) -> DeploymentPlanResponse:
        valid = self.repo.deployable_zones()
        if req.zone not in valid:
            raise UnknownZoneError(req.zone, valid)
        cand = self.repo.segments_in_zone(req.zone)
        labels = {
            r.physical_id: _label(r.name, r.junction, req.zone, r.physical_id)
            for r in cand.itertuples()
        }
        stops = [
            Stop(
                physical_id=r.physical_id, lat=float(r.centroid_lat), lon=float(r.centroid_lon),
                # Utility = CII × bias-adjusted risk (prioritise predicted risk).
                priority_utility=float(_clean(r.cii)) * (float(_clean(r.risk)) + 0.01),
            )
            for r in cand.itertuples()
        ]
        result = optimise_routes(
            stops, n_units=req.n_units, shift_minutes=req.shift_minutes,
            dwell_minutes=req.dwell_minutes, speed_kmph=req.speed_kmph,
        )
        return DeploymentPlanResponse(
            zone=req.zone,
            routes=[
                RouteModel(
                    unit=r.unit,
                    stops=[RouteStop(physical_id=p, label=labels.get(p, p)) for p in r.stops],
                    priority_utility=r.priority_utility, minutes=r.minutes,
                )
                for r in result.routes
            ],
            total_priority_utility=result.total_priority_utility,
            coverage_fraction=round(result.coverage_fraction, 4),
            solver=result.solver,
            method_caveats=result.method_caveats,
            requires_human_approval=result.requires_human_approval,
            provenance=self._provenance(),
        )

    # --- upliftment: graph context, what-if simulation, evidence-kinded context -------
    def neighborhood(self, segment_id: str, hops: int = 2) -> dict:
        """k-hop road-network neighbourhood of a segment (congestion propagates here)."""
        segs = self.repo.all_segments()
        if segment_id not in set(segs["physical_id"]):
            return {"segment_id": segment_id, "found": False, "neighbors": []}
        names = segs.set_index("physical_id")["name"].to_dict()
        nbrs = k_hop_neighborhood(segment_id, segs, hops)
        return {
            "segment_id": segment_id,
            "found": True,
            "hops": hops,
            "neighbors": [{"physical_id": p, "name": names.get(p), "hop": h} for p, h in nbrs],
            "provenance": self._provenance().model_dump(),
        }

    def simulate_blockage(
        self, segment_id: str, lanes_blocked: int = 1, minutes: int = 45, hops: int = 2
    ) -> SimulationResult | None:
        """What-if: illegal parking blocks lane(s) on a segment → modelled spillover."""
        segs = self.repo.all_segments()
        return simulate_parking_blockage(
            segment_id, segs, lanes_blocked=lanes_blocked, minutes=minutes, hops=hops
        )

    def segment_history(self, segment_id: str) -> dict:
        """Hour-of-week observed-enforcement profile for a segment (when, not just where)."""
        df = self.repo.hour_of_week(segment_id)
        return {
            "segment_id": segment_id,
            "hour_of_week": [{"hour_of_week": int(r.hour_of_week), "count": int(r.count)} for r in df.itertuples()],
            "provenance": self._provenance().model_dump(),
        }

    def segment_context(
        self, segment_id: str, *, run_simulation: bool = False, lanes_blocked: int = 1, minutes: int = 45
    ) -> TrafficContext | None:
        """Evidence-kinded Traffic Context for one segment (observed/predicted/simulated/missing)."""
        return build_segment_context(
            self.repo, segment_id, run_simulation=run_simulation,
            lanes_blocked=lanes_blocked, minutes=minutes,
        )
