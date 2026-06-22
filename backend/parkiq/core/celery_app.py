"""Celery application — the worker/scheduler runtime. Redis is the broker + result
backend. Heavy compute (ETL, training, publishing) runs here, never inside an HTTP
request. Tasks are thin wrappers that delegate to the same job functions the CLI uses,
each recorded through the job lifecycle.

    celery -A parkiq.core.celery_app worker --loglevel=info        # worker process
    celery -A parkiq.core.celery_app beat   --loglevel=info        # scheduler process
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from parkiq.core.config import get_settings

_s = get_settings()
celery_app = Celery("parkiq", broker=_s.redis_url, backend=_s.redis_url)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,                 # redeliver if a worker dies mid-task
    worker_prefetch_multiplier=1,        # heavy tasks: one at a time per worker
    task_default_queue="parkiq",
    timezone="UTC",
)


@celery_app.task(name="parkiq.pipeline", bind=True)
def pipeline_task(self, bbox: list | None = None, max_rows: int | None = None) -> dict:
    """The ONE mutating pipeline: ETL → train → publish, in order, under a Redis lock so
    two runs never mutate the gold/serving state concurrently. run_job re-raises on
    failure, so a failed step aborts the chain (no train/publish on stale artifacts).
    """
    import redis

    from parkiq.core.config import get_settings
    from parkiq.core.jobs import run_job
    from parkiq.db.serving import publish_all
    from parkiq.ingestion.run import run as run_etl
    from parkiq.models.train import train as run_train

    s = get_settings()
    lock = redis.Redis.from_url(s.redis_url).lock("parkiq:pipeline", timeout=6 * 3600)
    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "pipeline already running"}
    try:
        run_job("etl", lambda: run_etl(bbox=tuple(bbox) if bbox else None, max_rows=max_rows))
        run_job("train", run_train)
        if not s.offline:
            run_job("publish", publish_all)
        return {"status": "succeeded"}
    finally:
        try:
            lock.release()
        except redis.exceptions.LockError:
            pass


# Scheduler (Celery beat) — one daily pipeline, not three racing tasks.
celery_app.conf.beat_schedule = {
    "daily-pipeline": {"task": "parkiq.pipeline", "schedule": crontab(hour=2, minute=0)},
}
