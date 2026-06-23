"""HTTP routers — thin: parse → call a service → return. No business logic, no SQL,
no model code. Static paths are declared before parameterised ones to avoid collisions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from margadrishti.api.deps import get_service
from margadrishti.context.compiler import TrafficContext
from margadrishti.simulate.flow import SimulationResult
from margadrishti.api.models import (
    AreaDeploymentPlanRequest,
    AreaDeploymentPlanResponse,
    AreaSelectionRequest,
    AreaSummaryResponse,
    CiiMapResponse,
    DeploymentPlanRequest,
    DeploymentPlanResponse,
    ForecastResponse,
    SegmentDetail,
    TimeSlicedCiiResponse,
    TrendsResponse,
)
from margadrishti.api.services import MargadrishtiService, UnknownZoneError

router = APIRouter()


class BlockageRequest(BaseModel):
    segment_id: str
    lanes_blocked: int = Field(default=1, ge=1, le=4)
    minutes: int = Field(default=45, ge=5, le=240)
    hops: int = Field(default=2, ge=1, le=4)


@router.get("/segments/cii", response_model=CiiMapResponse, tags=["map"])
def segments_cii(
    limit: int = Query(2000, ge=1, le=20000),
    zone: str | None = None,
    svc: MargadrishtiService = Depends(get_service),
) -> CiiMapResponse:
    return svc.cii_map(limit=limit, zone=zone)


@router.get("/segments/cii/hourly", response_model=TimeSlicedCiiResponse, tags=["map"])
def segments_cii_hourly(
    hour: int | None = Query(None, ge=0, le=23, description="IST hour-of-day 0–23"),
    day_of_week: int | None = Query(None, ge=0, le=6, description="Monday=0 … Sunday=6"),
    zone: str | None = None,
    limit: int = Query(2000, ge=1, le=20000),
    svc: MargadrishtiService = Depends(get_service),
) -> TimeSlicedCiiResponse:
    """Time-sliced observed-enforcement intensity (not prevalence, not per-hour CII)."""
    return svc.cii_map_hourly(hour=hour, day_of_week=day_of_week, zone=zone, limit=limit)


@router.get("/forecast", response_model=ForecastResponse, tags=["forecast"])
def forecast(
    limit: int = Query(50, ge=1, le=2000),
    zone: str | None = None,
    svc: MargadrishtiService = Depends(get_service),
) -> ForecastResponse:
    return svc.forecast(limit=limit, zone=zone)


@router.get("/analytics/trends", response_model=TrendsResponse, tags=["analytics"])
def trends(svc: MargadrishtiService = Depends(get_service)) -> TrendsResponse:
    return svc.zone_trends()


@router.get("/zones", tags=["deployment"])
def zones(svc: MargadrishtiService = Depends(get_service)) -> dict:
    """Deployable jurisdictions (sentinels like 'No Police Station' are excluded)."""
    return {"zones": svc.repo.deployable_zones()}


@router.post("/deployment/plan", response_model=DeploymentPlanResponse, tags=["deployment"])
def deployment_plan(
    req: DeploymentPlanRequest, svc: MargadrishtiService = Depends(get_service)
) -> DeploymentPlanResponse:
    try:
        return svc.deployment_plan(req)
    except UnknownZoneError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": f"unknown zone {e.zone!r}", "valid_zones": e.valid},
        ) from e


@router.post("/area/summary", response_model=AreaSummaryResponse, tags=["map"])
def area_summary(
    req: AreaSelectionRequest, svc: MargadrishtiService = Depends(get_service)
) -> AreaSummaryResponse:
    """Geofence/lasso area select → in-area segment summary (centroid-in-polygon)."""
    return svc.area_summary(req)


@router.post("/area/deployment/plan", response_model=AreaDeploymentPlanResponse, tags=["deployment"])
def area_deployment_plan(
    req: AreaDeploymentPlanRequest, svc: MargadrishtiService = Depends(get_service)
) -> AreaDeploymentPlanResponse:
    """Geofence/lasso area select -> advisory patrol plan."""
    return svc.area_deployment_plan(req)


@router.get("/segments/{physical_id}/neighborhood", tags=["graph"])
def segment_neighborhood(
    physical_id: str, hops: int = Query(2, ge=1, le=4), svc: MargadrishtiService = Depends(get_service)
) -> dict:
    return svc.neighborhood(physical_id, hops=hops)


@router.get("/context/segment/{physical_id}", response_model=TrafficContext, tags=["context"])
def segment_context(
    physical_id: str,
    simulate: bool = False,
    lanes_blocked: int = Query(1, ge=1, le=4),
    minutes: int = Query(45, ge=5, le=240),
    svc: MargadrishtiService = Depends(get_service),
) -> TrafficContext:
    ctx = svc.segment_context(
        physical_id, run_simulation=simulate, lanes_blocked=lanes_blocked, minutes=minutes
    )
    if ctx is None:
        raise HTTPException(status_code=404, detail="segment not found")
    return ctx


@router.post("/simulate/blockage", response_model=SimulationResult, tags=["simulate"])
def simulate_blockage(
    req: BlockageRequest, svc: MargadrishtiService = Depends(get_service)
) -> SimulationResult:
    res = svc.simulate_blockage(
        req.segment_id, lanes_blocked=req.lanes_blocked, minutes=req.minutes, hops=req.hops
    )
    if res is None:
        raise HTTPException(status_code=404, detail="segment not found")
    return res


@router.get("/segments/{physical_id}", response_model=SegmentDetail, tags=["map"])
def segment_detail(
    physical_id: str, svc: MargadrishtiService = Depends(get_service)
) -> SegmentDetail:
    detail = svc.segment_detail(physical_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="segment not found")
    return detail
