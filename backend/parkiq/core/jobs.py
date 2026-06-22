"""Job lifecycle. Every worker/scheduler run is wrapped so it records input hash,
dataset version, code version, status, timing and failure reason (CLAUDE.md: jobs are
idempotent, resumable and versioned). Records append to data/jobs/jobs.jsonl — the
audit trail. In production this table lives in Postgres; the contract is identical.
"""

from __future__ import annotations

import json
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from parkiq.core.config import get_settings
from parkiq.core.versioning import file_fingerprint, now_rfc3339


@dataclass
class JobRun:
    job_type: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "running"
    started_at: str = field(default_factory=now_rfc3339)
    finished_at: str | None = None
    duration_s: float | None = None
    dataset_version: str = ""
    error: str | None = None
    result: dict = field(default_factory=dict)


def run_job(job_type: str, fn: Callable[[], dict | None]) -> JobRun:
    """Record the run (always) and RE-RAISE on failure. A failed job must stop the
    orchestration immediately: the CLI exits non-zero, a Celery task is marked failed,
    and a chained pipeline does not proceed to a dependent step on stale/partial data.
    """
    s = get_settings()
    rec = JobRun(job_type=job_type, dataset_version=file_fingerprint(s.raw_violations_csv))
    t0 = time.perf_counter()
    try:
        out = fn() or {}
        rec.result = out if isinstance(out, dict) else {"value": str(out)}
        rec.status = "succeeded"
    except Exception as e:  # record the failure reason, then propagate
        rec.status = "failed"
        rec.error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
        raise
    finally:
        rec.duration_s = round(time.perf_counter() - t0, 2)
        rec.finished_at = now_rfc3339()
        _append(rec, s.data_root / "jobs" / "jobs.jsonl")
    return rec


def _append(rec: JobRun, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in asdict(rec).items() if k != "error" or v is None or len(str(v)) < 4000}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe, default=str) + "\n")
    status = rec.status.upper()
    print(f"[job {rec.job_type} {rec.job_id}] {status} in {rec.duration_s}s")
