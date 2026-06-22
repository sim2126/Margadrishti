.PHONY: install etl train publish worker scheduler api test lint stack

install:
	pip install -e ".[dev]"

# --- worker process (heavy compute; never inside HTTP) ---
etl:            ## raw CSV → gold artifacts (Parquet)
	python -m margadrishti.worker etl

train:          ## evaluate ladder (both gates), emit bias-adjusted risk, recompute CII
	python -m margadrishti.worker train

publish:        ## load gold → PostGIS serving tables (needs POSTGIS_DSN)
	python -m margadrishti.worker publish

worker:         ## etl + train (+ publish if not offline), job-lifecycle wrapped
	python -m margadrishti.worker all

scheduler:      ## one-shot daily chain (Celery beat runs this in production)
	python -m margadrishti.scheduler --once

# --- API process (serves precomputed results only) ---
api:            ## serve FastAPI on :8000 (tier selected by MARGA_OFFLINE)
	uvicorn margadrishti.api.app:app --reload --port 8000

test:           ## PYTEST_DISABLE_PLUGIN_AUTOLOAD avoids unrelated 3rd-party plugin crashes
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest

lint:
	ruff check margadrishti && mypy margadrishti

stack:          ## full production runtime: PostGIS + Redis + API + worker + beat + Martin
	docker compose -f ../docker-compose.yml up --build
