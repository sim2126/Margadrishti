"""Direct (Celery-free) runner for the heavy compute that must never touch an HTTP
request: ingestion/ETL, map-matching, features, training, publishing. Used by the
reproducibility/CI tier and for one-shot local runs. In production the SAME job
functions run as Celery tasks (margadrishti.core.celery_app); the bodies are identical.

    python -m margadrishti.worker etl [--bbox W,S,E,N] [--max-rows N]
    python -m margadrishti.worker train
    python -m margadrishti.worker publish     # load gold → PostGIS (needs POSTGIS_DSN)
    python -m margadrishti.worker all         # etl + train (+ publish if not offline)
"""

from __future__ import annotations

import argparse

from margadrishti.core.config import get_settings
from margadrishti.core.jobs import run_job
from margadrishti.ingestion.run import _parse_bbox, run as run_etl
from margadrishti.models.train import train as run_train


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", choices=["etl", "train", "publish", "all"])
    ap.add_argument("--bbox", default=None, help="west,south,east,north")
    ap.add_argument("--max-rows", type=int, default=None)
    args = ap.parse_args()
    # CLI --bbox wins; else fall back to MARGA_ETL_BBOX (lets the compose bootstrap bound
    # the first run without a full-city OSM download). Empty env = derive from data.
    bbox = _parse_bbox(args.bbox) or _parse_bbox(get_settings().etl_bbox or None)

    if args.task in ("etl", "all"):
        run_job("etl", lambda: run_etl(bbox=bbox, max_rows=args.max_rows))
    if args.task in ("train", "all"):
        run_job("train", run_train)
    if args.task == "publish" or (args.task == "all" and not get_settings().offline):
        from margadrishti.db.serving import publish_all

        run_job("publish", publish_all)


if __name__ == "__main__":
    main()
