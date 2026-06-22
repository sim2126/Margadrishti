"""FastAPI entrypoint (API process). Route handlers stay THIN: parse → call a service →
serialise. No business logic, no SQL, no model code here (CLAUDE.md modularity rule).
The API never downloads OSM, trains, or runs ETL — that is the worker's job.

Privacy: no endpoint returns vehicle numbers or officer/device raw ids. Deployment
recommendations are advisory; a human approves (DeploymentPlanResponse carries the flag).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from parkiq.api.copilot_routes import router as copilot_router
from parkiq.api.deps import get_service
from parkiq.api.routes import router as api_router

app = FastAPI(title="ParkIQ API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(api_router)
app.include_router(copilot_router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    m = get_service().repo.manifest()
    return {
        "status": "ok",
        "dataset_version": m.get("etl", {}).get("dataset_version", "unknown"),
        "model_version": m.get("model", {}).get("model_version", "unknown"),
        "as_of": m.get("model", {}).get("as_of", "unknown"),
        "n_segments": m.get("etl", {}).get("n_segments"),
        "in_scope_rows": m.get("etl", {}).get("n_in_scope_rows"),
    }
