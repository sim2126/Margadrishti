"""Application service layer — the single source of business logic. API routes AND the
copilot call THESE methods (never loop back through HTTP). Each method composes the
read-only repository (and the pure optimiser) and attaches full provenance.
"""

from __future__ import annotations

import hashlib
import math

import pandas as pd

from margadrishti.api.models import (
    AreaDeploymentPlanRequest,
    AreaDeploymentPlanResponse,
    AreaSegment,
    AreaSelectionRequest,
    AreaSummaryResponse,
    CiiMapResponse,
    CiiSegment,
    DeploymentPlanRequest,
    DeploymentPlanResponse,
    EvalMetric,
    EvaluationSummaryResponse,
    ForecastItem,
    ForecastResponse,
    Provenance,
    RouteModel,
    RouteStop,
    SegmentDetail,
    TimeSlicedCiiResponse,
    TimeSlicedSegment,
    TrendsResponse,
    ZoneTrend,
)
from margadrishti.api.repository import GoldRepository
from margadrishti.context.compiler import TrafficContext, build_segment_context
from margadrishti.core.versioning import now_rfc3339
from margadrishti.optimize.deployment import Stop, optimise_routes
from margadrishti.simulate.flow import SimulationResult, k_hop_neighborhood, simulate_parking_blockage

_CII_NOTE = "CII is a prioritisation proxy, not a causal congestion measure."

# Area selection scans served segments and tests each centroid against the drawn polygon.
# Fine at bounded/city scale; full-city production should push this to PostGIS ST_Contains.
AREA_SCAN_LIMIT = 100_000


def _point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """Ray-casting test. `poly` is [(lon, lat), ...]; (x, y) is (lon, lat).
    Planar test in lon/lat — accurate for a city-scale lasso. Pure stdlib (no shapely)."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _area_id(poly: list[tuple[float, float]]) -> str:
    """Stable id for a drawn polygon (same ring → same id) for client correlation/audit."""
    key = ";".join(f"{x:.5f},{y:.5f}" for x, y in poly)
    return "area-" + hashlib.sha1(key.encode()).hexdigest()[:10]


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


def _text(v):
    """Coerce a possibly-NaN cell to str | None. Full-city OSM data carries missing road
    names/zones as float NaN (not None), which crashes .strip() and pydantic str fields."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return str(v)


def _label(name, junction, zone, physical_id: str) -> str:
    """Operationally distinguishable label so several segments on one road don't all
    read as just 'Hosur Road'. Stable short code disambiguates same name + place."""
    base = (_text(name) or "Unnamed road").strip()
    place = (_text(junction) or _text(zone) or "").strip()
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

    @staticmethod
    def _cii_segment(r) -> CiiSegment:
        """Build a CiiSegment from a cii⋈dim row (shared by the map and area endpoints)."""
        return CiiSegment(
            physical_id=r.physical_id, name=_text(r.name),
            label=_label(r.name, r.junction, r.zone, r.physical_id),
            junction=_text(r.junction), highway=_text(r.highway), zone=_text(r.zone),
            cii=round(float(r.cii), 4), observed_count=int(r.observed_count),
            approval_rate=_clean(r.approval_rate, None),
            centroid_lat=float(r.centroid_lat), centroid_lon=float(r.centroid_lon),
            component_risk=round(float(r.cii_component__risk), 4),
            component_centrality=round(float(r.cii_component__centrality), 4),
            component_obstruction=round(float(r.cii_component__obstruction), 4),
        )

    def cii_map(self, limit: int = 2000, zone: str | None = None) -> CiiMapResponse:
        df = self.repo.cii_segments(limit=limit, zone=zone)
        interim = bool(df["cii_risk_is_interim_biased"].iloc[0]) if len(df) else False
        segs = [self._cii_segment(r) for r in df.itertuples()]
        return CiiMapResponse(segments=segs, provenance=self._provenance(interim))

    def area_summary(self, req: AreaSelectionRequest) -> AreaSummaryResponse:
        """Geofence/lasso select: keep segments whose centroid falls inside the drawn polygon,
        then summarise (count, observed enforcement, mean/top CII, zones, ranked candidates).
        Lets a commander select a market/metro corridor without knowing station labels.
        Centroid-in-polygon at this scale; full-city production should use PostGIS ST_Contains."""
        poly = [(p.lon, p.lat) for p in req.polygon]
        df = self.repo.cii_with_risk(limit=AREA_SCAN_LIMIT)
        interim = bool(df["cii_risk_is_interim_biased"].iloc[0]) if len(df) else False
        segs = [
            AreaSegment(
                physical_id=r.physical_id, name=_text(r.name),
                label=_label(r.name, r.junction, r.zone, r.physical_id),
                junction=_text(r.junction), zone=_text(r.zone),
                cii=round(float(_clean(r.cii)), 4),
                observed_count=int(_clean(r.observed_count)),
                predicted_risk=_clean(r.predicted_risk, None),
                # Utility mirrors the deployment optimiser: CII × bias-adjusted predicted risk.
                priority_utility=round(float(_clean(r.cii)) * (float(_clean(r.predicted_risk)) + 0.01), 6),
                centroid_lat=float(r.centroid_lat), centroid_lon=float(r.centroid_lon),
            )
            for r in df.itertuples()
            if _point_in_polygon(float(r.centroid_lon), float(r.centroid_lat), poly)
        ]
        ciis = [s.cii for s in segs]
        ranked = sorted(segs, key=lambda s: s.cii, reverse=True)
        return AreaSummaryResponse(
            area_id=_area_id(poly),
            n_segments=len(segs),
            observed_count=sum(s.observed_count for s in segs),
            mean_cii=round(sum(ciis) / len(ciis), 4) if ciis else 0.0,
            max_cii=round(max(ciis), 4) if ciis else 0.0,
            zones=sorted({s.zone for s in segs if s.zone}),
            top_segments=ranked[: req.limit],
            provenance=self._provenance(interim),
        )

    def _area_segments_for_deployment(self, req: AreaSelectionRequest) -> tuple[str, list[AreaSegment], bool]:
        """Return all in-area segments for deployment candidate selection.

        Kept separate from `area_summary` because the summary is CII-ranked for map
        explanation, while deployment should candidate-rank by priority utility.
        """
        poly = [(p.lon, p.lat) for p in req.polygon]
        df = self.repo.cii_with_risk(limit=AREA_SCAN_LIMIT)
        interim = bool(df["cii_risk_is_interim_biased"].iloc[0]) if len(df) else False
        segs = [
            AreaSegment(
                physical_id=r.physical_id, name=_text(r.name),
                label=_label(r.name, r.junction, r.zone, r.physical_id),
                junction=_text(r.junction), zone=_text(r.zone),
                cii=round(float(_clean(r.cii)), 4),
                observed_count=int(_clean(r.observed_count)),
                predicted_risk=_clean(r.predicted_risk, None),
                priority_utility=round(float(_clean(r.cii)) * (float(_clean(r.predicted_risk)) + 0.01), 6),
                centroid_lat=float(r.centroid_lat), centroid_lon=float(r.centroid_lon),
            )
            for r in df.itertuples()
            if _point_in_polygon(float(r.centroid_lon), float(r.centroid_lat), poly)
        ]
        return _area_id(poly), segs, interim

    def cii_map_hourly(
        self,
        hour: int | None = None,
        day_of_week: int | None = None,
        zone: str | None = None,
        limit: int = 2000,
    ) -> TimeSlicedCiiResponse:
        """Time-sliced OBSERVED-ENFORCEMENT intensity for the map/list scrubber.

        Honest by construction: serves the observed hour-of-week signal (labelled as such),
        not a fabricated per-hour CII. `hour_intensity` is the window count scaled to the
        busiest segment in the set, so the map can shade/elevate and the list can re-rank.
        """
        df = self.repo.hourly_observed(hour=hour, day_of_week=day_of_week, zone=zone, limit=limit)
        interim = bool(df["cii_risk_is_interim_biased"].iloc[0]) if len(df) else False
        max_w = float(df["window_count"].max()) if len(df) else 0.0
        segs = [
            TimeSlicedSegment(
                physical_id=r.physical_id, name=_text(r.name),
                label=_label(r.name, r.junction, r.zone, r.physical_id),
                junction=_text(r.junction), zone=_text(r.zone),
                cii=round(float(_clean(r.cii)), 4),
                window_observed_count=int(_clean(r.window_count)),
                hour_intensity=round(float(_clean(r.window_count)) / max_w, 4) if max_w > 0 else 0.0,
                centroid_lat=float(r.centroid_lat), centroid_lon=float(r.centroid_lon),
            )
            for r in df.itertuples()
        ]
        return TimeSlicedCiiResponse(
            hour=hour, day_of_week=day_of_week, segments=segs,
            provenance=self._provenance(interim),
        )

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
            physical_id=physical_id, name=_text(d.get("name")),
            label=_label(d.get("name"), d.get("junction"), d.get("zone"), physical_id),
            junction=_text(d.get("junction")), zone=_text(d.get("zone")),
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
                physical_id=r.physical_id, name=_text(r.name),
                label=_label(r.name, r.junction, r.zone, r.physical_id),
                junction=_text(r.junction), zone=_text(r.zone),
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
                zone=_text(r.zone), n_segments=int(r.n_segments),
                observed_count=int(_clean(r.observed_count)),
                mean_cii=round(float(_clean(r.mean_cii)), 4),
            )
            for r in df.itertuples()
        ]
        return TrendsResponse(zones=zones, provenance=self._provenance())

    @staticmethod
    def _eval_metric(row: dict) -> EvalMetric:
        p_at = row.get("precision_at_k", {}) or {}
        r_at = row.get("recall_at_k", {}) or {}
        return EvalMetric(
            model=str(row.get("model", "unknown")),
            pr_auc=round(float(row.get("pr_auc", 0.0)), 4),
            precision_at_25=round(float(p_at.get("25", 0.0)), 4),
            recall_at_25=round(float(r_at.get("25", 0.0)), 4),
            n_test_rows=int(row.get("n_test_rows", 0) or 0),
        )

    def evaluation_summary(self) -> EvaluationSummaryResponse:
        report = self.repo.eval_report()
        manifest = self.repo.manifest()
        etl, model = manifest.get("etl", {}), manifest.get("model", {})
        rolling = [self._eval_metric(r) for r in report.get("rolling_origin", [])]
        held_out = [self._eval_metric(r) for r in report.get("held_out_zone", [])]
        held_lgbm = next((m for m in held_out if m.model.startswith("lightgbm")), None)
        baseline_best = max(
            (m for m in held_out if not m.model.startswith("lightgbm")),
            key=lambda m: m.pr_auc,
            default=None,
        )
        findings = [
            (
                f"Full-city run: {int(etl.get('n_input_rows', 0)):,} input rows, "
                f"{int(etl.get('n_in_scope_rows', 0)):,} in-scope rows, "
                f"{int(etl.get('n_segments', 0)):,} physical segments."
            ),
            f"Current model winner: {report.get('winner', model.get('winner', 'unknown'))}.",
        ]
        if held_lgbm and baseline_best:
            findings.append(
                f"Held-out-zone gate: LightGBM PR-AUC {held_lgbm.pr_auc:.3f} vs "
                f"best baseline {baseline_best.pr_auc:.3f}."
            )
        findings.append(
            "Traffic-flow impact is still a prioritisation/simulation estimate because the organiser data has no speed or volume feed."
        )
        return EvaluationSummaryResponse(
            model_version=str(report.get("model_version", model.get("model_version", "unknown"))),
            winner=str(report.get("winner", model.get("winner", "unknown"))),
            a_candidate_shipped=bool(report.get("a_candidate_shipped", model.get("lightgbm_ships", False))),
            n_input_rows=int(etl.get("n_input_rows", 0) or 0),
            n_in_scope_rows=int(etl.get("n_in_scope_rows", 0) or 0),
            n_segments=int(etl.get("n_segments", 0) or 0),
            road_network_version=str(etl.get("road_network_version", "unknown")),
            rolling_origin=rolling,
            held_out_zone=held_out,
            feature_importance={k: round(float(v), 4) for k, v in (report.get("feature_importance", {}) or {}).items()},
            key_findings=findings,
            provenance=self._provenance(bool(model.get("lightgbm_ships") is False)),
        )

    def deployment_plan(self, req: DeploymentPlanRequest) -> DeploymentPlanResponse:
        valid = self.repo.deployable_zones()
        if req.zone not in valid:
            raise UnknownZoneError(req.zone, valid)
        cand = self.repo.segments_in_zone(req.zone)
        stop_meta = {
            r.physical_id: {
                "label": _label(r.name, r.junction, req.zone, r.physical_id),
                "lat": float(r.centroid_lat),
                "lon": float(r.centroid_lon),
            }
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
                    stops=[
                        RouteStop(
                            physical_id=p,
                            label=stop_meta.get(p, {}).get("label", p),
                            centroid_lat=stop_meta.get(p, {}).get("lat"),
                            centroid_lon=stop_meta.get(p, {}).get("lon"),
                        )
                        for p in r.stops
                    ],
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

    def area_deployment_plan(self, req: AreaDeploymentPlanRequest) -> AreaDeploymentPlanResponse:
        """Geofence/lasso select -> advisory patrol plan.

        `zone` remains a jurisdiction concept. A drawn polygon is an operator-defined
        planning area, so this response exposes `area_id` and touched `zones` separately.
        """
        area_id, segs, interim = self._area_segments_for_deployment(req)
        candidates = sorted(segs, key=lambda s: s.priority_utility, reverse=True)[: req.limit]
        stop_meta = {
            s.physical_id: {"label": s.label, "lat": s.centroid_lat, "lon": s.centroid_lon}
            for s in candidates
        }
        stops = [
            Stop(
                physical_id=s.physical_id,
                lat=s.centroid_lat,
                lon=s.centroid_lon,
                priority_utility=s.priority_utility,
            )
            for s in candidates
        ]
        result = optimise_routes(
            stops,
            n_units=req.n_units,
            shift_minutes=req.shift_minutes,
            dwell_minutes=req.dwell_minutes,
            speed_kmph=req.speed_kmph,
        )
        return AreaDeploymentPlanResponse(
            area_id=area_id,
            n_segments=len(segs),
            n_candidate_segments=len(stops),
            zones=sorted({s.zone for s in segs if s.zone}),
            routes=[
                RouteModel(
                    unit=r.unit,
                    stops=[
                        RouteStop(
                            physical_id=p,
                            label=stop_meta.get(p, {}).get("label", p),
                            centroid_lat=stop_meta.get(p, {}).get("lat"),
                            centroid_lon=stop_meta.get(p, {}).get("lon"),
                        )
                        for p in r.stops
                    ],
                    priority_utility=r.priority_utility,
                    minutes=r.minutes,
                )
                for r in result.routes
            ],
            total_priority_utility=result.total_priority_utility,
            coverage_fraction=round(result.coverage_fraction, 4),
            solver=result.solver,
            method_caveats=result.method_caveats,
            requires_human_approval=result.requires_human_approval,
            provenance=self._provenance(interim),
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
