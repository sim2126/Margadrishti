.PHONY: install etl train publish worker scheduler api test lint stack

install:
	pip install -e ".[dev]"

# --- worker process (heavy compute; never inside HTTP) ---
etl:            ## raw CSV → gold artifacts (Parquet)
	python -m parkiq.worker etl

train:          ## evaluate ladder (both gates), emit bias-adjusted risk, recompute CII
	python -m parkiq.worker train

publish:        ## load gold → PostGIS serving tables (needs POSTGIS_DSN)
	python -m parkiq.worker publish

worker:         ## etl + train (+ publish if not offline), job-lifecycle wrapped
	python -m parkiq.worker all

scheduler:      ## one-shot daily chain (Celery beat runs this in production)
	python -m parkiq.scheduler --once

# --- API process (serves precomputed results only) ---
api:            ## serve FastAPI on :8000 (tier selected by PARKIQ_OFFLINE)
	uvicorn parkiq.api.app:app --reload --port 8000

test:           ## PYTEST_DISABLE_PLUGIN_AUTOLOAD avoids unrelated 3rd-party plugin crashes
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest

lint:
	ruff check parkiq && mypy parkiq

stack:          ## full production runtime: PostGIS + Redis + API + worker + beat + Martin
	docker compose -f ../docker-compose.yml up --build
