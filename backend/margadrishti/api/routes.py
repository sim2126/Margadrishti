"""HTTP routers — thin: parse → call a service → return. No business logic, no SQL,
no model code. Static paths are declared before parameterised ones to avoid collisions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from margadrishti.api.deps import get_service
from margadrishti.api.models import (
    CiiMapResponse,
    DeploymentPlanRequest,
    DeploymentPlanResponse,
    ForecastResponse,
    SegmentDetail,
    TrendsResponse,
)
from margadrishti.api.services import MargadrishtiService, UnknownZoneError

router = APIRouter()


@router.get("/segments/cii", response_model=CiiMapResponse, tags=["map"])
def segments_cii(
    limit: int = Query(2000, ge=1, le=20000),
    zone: str | None = None,
    svc: MargadrishtiService = Depends(get_service),
) -> CiiMapResponse:
    return svc.cii_map(limit=limit, zone=zone)


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


@router.get("/segments/{physical_id}", response_model=SegmentDetail, tags=["map"])
def segment_detail(
    physical_id: str, svc: MargadrishtiService = Depends(get_service)
) -> SegmentDetail:
    detail = svc.segment_detail(physical_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="segment not found")
    return detail
