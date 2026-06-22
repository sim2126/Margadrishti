# Margadrishti Backend

Layered, modular Python backend. Dependencies flow **one direction only** — a lower
layer never imports a higher one. Every layer is independently testable behind a typed
interface. See the root [`CLAUDE.md`](../CLAUDE.md) for the binding engineering/model rules.

```
margadrishti/
├── core/         # config, schemas, time, storage, versioning, jobs, celery_app  (depends on nothing)
├── ingestion/    # raw CSV → validated typed records → bronze Parquet (+ PII split)
├── geo/          # OSM physical road segments · H3 attachment · point→segment map-matching
├── features/     # segment × time-bucket feature store + leakage-safe panel
├── models/       # forecaster ladder: baselines → LightGBM (→ ST-GNN) + evaluation gates
├── cii/          # Congestion-Impact Index (transparent prioritisation proxy)
├── optimize/     # constrained patrol-deployment optimiser (OR-Tools)
├── db/           # PostGIS schema (DDL, GIST index, RLS) + gold→PostGIS publisher
├── api/          # FastAPI: thin routes → service layer → repository (gold OR PostGIS)
└── copilot/      # Claude tool-use agent over the service layer (model IDs from env)
worker.py · scheduler.py · core/celery_app.py   # process types (direct CLI + Celery)
```

## Process types & two persistence tiers

| Process | Runs | Backed by |
|---|---|---|
| **API** | serves precomputed CII/forecast/plans; copilot | reads serving tier |
| **Worker** (Celery) | ETL, map-match, features, train, publish | writes gold + PostGIS |
| **Scheduler** (Celery beat) | daily ingest → retrain → publish | enqueues worker tasks |
| **Tiles** (Martin) | MVT vector tiles at city scale | PostGIS `tiles_cii`/`segments_dim` |

- **Production serving tier:** PostGIS (typed tables, GIST spatial index, zone-scoped
  row-level security). The API selects this when `MARGA_OFFLINE=false`.
- **Reproducibility/CI tier:** versioned Parquet + DuckDB — ETL/tests run with no
  external services. Same repository interface; selected when `MARGA_OFFLINE=true`.

## Core design decisions (and why)

- **Road segment is the source entity.** Violations are map-matched to *directed* OSM
  segments so opposite carriageways / parallel roads are never conflated. H3 IDs are
  *attached* to segments only for aggregation, heatmaps, and display.
- **Medallion storage.** `bronze` (validated raw) → `silver` (cleaned, geo-resolved) →
  `gold` (feature/serving tables). Gold is published to **PostGIS** for production
  serving; the versioned Parquet/DuckDB copy is the reproducibility/CI tier.
- **PII boundary lives in `core`.** Vehicle numbers and officer/device identifiers are
  split out at ingestion into a restricted store and never enter features, the API,
  the UI, or LLM context.
- **Observed enforcement ≠ prevalence.** Counts are exposed as *observed enforcement
  density*; models condition on enforcement-exposure features.
- **UTC in, Asia/Kolkata for features.** Timestamps stored UTC; all operational
  (hour/day-of-week) features derived in IST via `core.timeutils`.

## Data flow

```
ingestion.load_violations(csv)     → bronze/violations.parquet  (+ PII → restricted)
geo.build_segments / map-match     → silver/segments.parquet, silver/violations_matched.parquet
features (aggregate + panel)       → gold/segment_features, segment_hour_of_week, panel
models.train (ladder + gates)      → gold/predictions.parquet, gold/cii.parquet, manifest.json
db.serving.publish_all             → PostGIS (segments_dim, cii, …) → api · Martin tiles · copilot
```

## Run

**Production stack (one command):**
```bash
docker compose up        # PostGIS + Redis + API(:8000) + worker + scheduler + Martin(:3000)
                         # bootstrap runs ETL→train→publish, then the API serves from PostGIS
```

**Reproducibility / CI tier (no external services):**
```bash
make install             # pip install -e .[dev]
make worker              # ETL → train (gold Parquet + manifest)
make api                 # FastAPI on :8000 (reads gold via DuckDB)
make test                # pytest (offline)
```
