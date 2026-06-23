"""FastAPI entrypoint (API process). Route handlers stay THIN: parse → call a service →
serialise. No business logic, no SQL, no model code here (CLAUDE.md modularity rule).
The API never downloads OSM, trains, or runs ETL — that is the worker's job.

Privacy: no endpoint returns vehicle numbers or officer/device raw ids. Deployment
recommendations are advisory; a human approves (DeploymentPlanResponse carries the flag).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from margadrishti.api.deps import get_service
from margadrishti.api.copilot_routes import router as copilot_router
from margadrishti.api.routes import router as api_router
from margadrishti.core.config import get_settings

log = structlog.get_logger(__name__)


def _store_mode() -> str:
    s = get_settings()
    return "postgis" if (not s.offline and (s.postgis_read_dsn or s.postgis_dsn)) else "gold"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Margadrishti API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
        request.state.request_id = request_id
        started = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = getattr(response, "status_code", 500)
            log.info(
                "api_request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=elapsed_ms,
            )
            if response is not None:
                response.headers["x-request-id"] = request_id

    app.include_router(api_router)
    app.include_router(copilot_router)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Defence in depth: any unhandled error returns a generic body — never a traceback,
        # SDK error text, or settings. Log the exception type only (no secrets, no message).
        rid = getattr(request.state, "request_id", None)
        log.error("unhandled_exception", error=type(exc).__name__, path=request.url.path, request_id=rid)
        return JSONResponse(status_code=500, content={"detail": "internal error", "request_id": rid})

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, Any]:
        m = get_service().repo.manifest()
        return {
            "status": "ok",
            "store": _store_mode(),
            "dataset_version": m.get("etl", {}).get("dataset_version", "unknown"),
            "model_version": m.get("model", {}).get("model_version", "unknown"),
            "as_of": m.get("model", {}).get("as_of", "unknown"),
            "n_segments": m.get("etl", {}).get("n_segments"),
            "in_scope_rows": m.get("etl", {}).get("n_in_scope_rows"),
        }

    @app.get("/ready", tags=["meta"])
    def ready() -> dict[str, Any]:
        """Deployment readiness: serving data must be queryable before traffic is routed."""
        checks: dict[str, Any] = {"store": _store_mode()}
        try:
            svc = get_service()
            manifest = svc.repo.manifest()
            checks["manifest"] = bool(manifest.get("etl") and manifest.get("model"))
            checks["zones"] = len(svc.repo.deployable_zones())
            checks["sample_cii_rows"] = len(svc.repo.cii_segments(limit=1))
        except Exception as e:  # pragma: no cover - exact DB/FS error differs by runtime
            checks["error"] = str(e)
            raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks}) from e
        if not checks["manifest"] or checks["zones"] < 1 or checks["sample_cii_rows"] < 1:
            raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
        return {"status": "ready", "checks": checks}

    return app


app = create_app()
