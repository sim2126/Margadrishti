"""Scheduler. In production this is Celery beat (see parkiq.core.celery_app.beat_schedule):

    celery -A parkiq.core.celery_app beat --loglevel=info

This module keeps a Celery-free `--once` runner for CI and one-shot operations, firing
the same job functions the beat schedule triggers (daily ingest → retrain → publish).

    python -m parkiq.scheduler --once
"""

from __future__ import annotations

import argparse

from parkiq.core.config import get_settings
from parkiq.core.jobs import run_job
from parkiq.ingestion.run import run as run_etl
from parkiq.models.train import train as run_train


def run_once() -> None:
    run_job("scheduled:ingest", run_etl)
    run_job("scheduled:retrain", run_train)
    if not get_settings().offline:
        from parkiq.db.serving import publish_all

        run_job("scheduled:publish", publish_all)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="fire the daily chain once and exit")
    ap.parse_args()
    run_once()
