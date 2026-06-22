# ParkIQ

**Parking Intelligence for Targeted Enforcement** — built for the Bengaluru Traffic Police
(Flipkart GRID, Theme 1: Parking-Induced Congestion).

ParkIQ turns the city's existing parking-violation records into a deployable enforcement
tool: it detects illegal-parking hotspots, quantifies their congestion impact, forecasts
risk, and recommends where to send patrols — all on data the city already collects, with
no new cameras or sensors.

## What's here

| Area | Stack |
|---|---|
| **Backend** | Python · FastAPI · PostGIS · Celery/Redis · LightGBM · OR-Tools · osmnx/H3 · DuckDB/Parquet |
| **Frontend** | Vite · React + TypeScript · Tailwind · deck.gl + MapLibre · TanStack Query |
| **Runtime** | `docker compose up` → PostGIS · Redis · API · worker · scheduler · Martin tiles |

- **Road segment is the modelling unit** (directed OSM segments; H3 for aggregation/render).
- **Congestion-Impact Index (CII)** — a transparent prioritisation proxy (topology ×
  obstruction × bias-adjusted risk), never a causal congestion claim.
- **Honest ML** — observed enforcement ≠ prevalence; a model ships only if it beats
  operational baselines on rolling-origin **and** held-out-zone gates.
- **Governance built in** — PII split at ingestion, provenance on every response,
  human approval before any deployment recommendation.

## Run

```bash
# Backend (reproducibility/CI tier — no external services)
cd backend && make install && make worker && make api      # API on :8000

# Frontend
cd frontend && npm install && npm run dev                  # UI on :5173

# Full production runtime
docker compose up --build
```

See `backend/README.md` and `frontend/README.md` for details.

> Datasets are not included in this repository (sensitive government data).
