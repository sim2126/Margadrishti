"""API response/request models. Every analytical response carries `Provenance` so the
UI and copilot can show source, as-of, dataset/feature/road-network/model versions and
the generation timestamp (RFC 3339 UTC)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Provenance(BaseModel):
    source: str = "margadrishti.gold"
    generated_at: str                      # RFC 3339 UTC (when this response was built)
    as_of: str                             # data horizon the artifacts reflect
    dataset_version: str = "unknown"
    feature_version: str = "unknown"
    road_network_version: str = "unknown"
    cii_version: str = "unknown"
    model_version: str = "unknown"
    cii_risk_is_interim_biased: bool = False
    note: str | None = None


class CiiSegment(BaseModel):
    physical_id: str
    name: str | None
    label: str                             # operationally distinguishable display label
    junction: str | None
    highway: str | None
    zone: str | None
    cii: float
    observed_count: int
    approval_rate: float | None
    centroid_lat: float
    centroid_lon: float
    component_risk: float
    component_centrality: float
    component_obstruction: float


class CiiMapResponse(BaseModel):
    segments: list[CiiSegment]
    provenance: Provenance


class TimeSlicedSegment(BaseModel):
    physical_id: str
    name: str | None
    label: str
    junction: str | None
    zone: str | None
    cii: float                             # all-day CII, kept for ranking continuity
    window_observed_count: int             # observed enforcement in the selected time window
    hour_intensity: float                  # window count normalised to [0,1] across the set
    centroid_lat: float
    centroid_lon: float


class TimeSlicedCiiResponse(BaseModel):
    hour: int | None = None                # IST hour-of-day 0–23 (None = all hours)
    day_of_week: int | None = None         # Monday=0 … Sunday=6 (None = all days)
    temporal_basis: str = "observed_enforcement_hour_of_week"
    is_observed_not_prevalence: bool = True
    note: str = (
        "Observed enforcement intensity by IST hour-of-week (when officers logged "
        "violations) — not prevalence, and not a per-hour CII. Reflects patrol exposure."
    )
    segments: list[TimeSlicedSegment]
    provenance: Provenance


class SegmentDetail(BaseModel):
    physical_id: str
    name: str | None
    label: str
    junction: str | None
    zone: str | None
    cii: float
    predicted_risk: float | None
    observed_count: int
    approved_count: float | None
    approval_rate: float | None
    n_officers: int | None
    active_hours: int | None
    why: dict[str, float]
    provenance: Provenance


class ForecastItem(BaseModel):
    physical_id: str
    name: str | None
    label: str
    junction: str | None
    zone: str | None
    risk: float
    cii: float | None
    centroid_lat: float
    centroid_lon: float


class ForecastResponse(BaseModel):
    items: list[ForecastItem]
    provenance: Provenance


class ZoneTrend(BaseModel):
    zone: str | None
    n_segments: int
    observed_count: int
    mean_cii: float


class TrendsResponse(BaseModel):
    label: str = "observed enforcement density (NOT prevalence)"
    zones: list[ZoneTrend]
    provenance: Provenance


class DeploymentPlanRequest(BaseModel):
    zone: str
    n_units: int = Field(ge=1, le=50)
    shift_minutes: int = Field(default=240, ge=30, le=720)
    dwell_minutes: int = Field(default=12, ge=1, le=60)
    speed_kmph: float = Field(default=18.0, gt=0, le=80)


class LonLat(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class AreaSelectionRequest(BaseModel):
    polygon: list[LonLat] = Field(
        min_length=3,
        description="GeoJSON-style polygon ring positions as lon/lat objects. Ring closure is optional.",
    )
    limit: int = Field(default=200, ge=1, le=20000)

    @model_validator(mode="after")
    def _has_area(self) -> "AreaSelectionRequest":
        pts = {(p.lon, p.lat) for p in self.polygon}
        if len(pts) < 3:
            raise ValueError("polygon must contain at least three distinct positions")
        return self


class AreaDeploymentPlanRequest(AreaSelectionRequest):
    n_units: int = Field(default=3, ge=1, le=50)
    shift_minutes: int = Field(default=240, ge=30, le=720)
    dwell_minutes: int = Field(default=12, ge=1, le=60)
    speed_kmph: float = Field(default=18.0, gt=0, le=80)


class AreaSegment(BaseModel):
    physical_id: str
    name: str | None
    label: str
    junction: str | None
    zone: str | None
    cii: float
    observed_count: int
    predicted_risk: float | None
    priority_utility: float
    centroid_lat: float
    centroid_lon: float


class AreaSummaryResponse(BaseModel):
    area_id: str
    method: str = "centroid_in_polygon"
    n_segments: int
    observed_count: int
    mean_cii: float
    max_cii: float
    zones: list[str]
    top_segments: list[AreaSegment]
    caveats: str = (
        "Area selection uses segment centroids within the drawn polygon. Observed counts "
        "are enforcement records, not true violation prevalence."
    )
    provenance: Provenance


class RouteStop(BaseModel):
    physical_id: str
    label: str
    centroid_lat: float | None = None
    centroid_lon: float | None = None


class RouteModel(BaseModel):
    unit: int
    stops: list[RouteStop]
    priority_utility: float
    minutes: float


class AreaDeploymentPlanResponse(BaseModel):
    area_id: str
    method: str = "centroid_in_polygon"
    n_segments: int
    n_candidate_segments: int
    zones: list[str]
    routes: list[RouteModel]
    total_priority_utility: float
    coverage_fraction: float
    solver: str
    method_caveats: str
    area_caveats: str = (
        "Area deployment uses segment centroids within the drawn polygon. It is an "
        "advisory patrol plan and must still be reviewed against jurisdiction boundaries."
    )
    requires_human_approval: bool = True
    provenance: Provenance


class DeploymentPlanResponse(BaseModel):
    zone: str
    routes: list[RouteModel]
    total_priority_utility: float
    coverage_fraction: float
    solver: str
    method_caveats: str
    requires_human_approval: bool = True
    provenance: Provenance


class EvalMetric(BaseModel):
    model: str
    pr_auc: float
    precision_at_25: float
    recall_at_25: float
    n_test_rows: int


class EvaluationSummaryResponse(BaseModel):
    model_version: str
    winner: str
    a_candidate_shipped: bool
    n_input_rows: int
    n_in_scope_rows: int
    n_segments: int
    road_network_version: str
    rolling_origin: list[EvalMetric]
    held_out_zone: list[EvalMetric]
    feature_importance: dict[str, float]
    key_findings: list[str]
    caveats: str = (
        "Evaluation ranks hotspot prediction quality. It does not prove measured "
        "traffic-flow reduction; organiser data has no speed or volume feed."
    )
    provenance: Provenance
