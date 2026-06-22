"""API response/request models. Every analytical response carries `Provenance` so the
UI and copilot can show source, as-of, dataset/feature/road-network/model versions and
the generation timestamp (RFC 3339 UTC)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    source: str = "parkiq.gold"
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


class RouteStop(BaseModel):
    physical_id: str
    label: str


class RouteModel(BaseModel):
    unit: int
    stops: list[RouteStop]
    priority_utility: float
    minutes: float


class DeploymentPlanResponse(BaseModel):
    zone: str
    routes: list[RouteModel]
    total_priority_utility: float
    coverage_fraction: float
    solver: str
    method_caveats: str
    requires_human_approval: bool = True
    provenance: Provenance
