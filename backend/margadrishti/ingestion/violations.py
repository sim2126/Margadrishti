"""Raw violations CSV → validated bronze, with the PII split enforced here.

Vectorised pandas (the file is ~298K rows; per-row pydantic would be too slow).
`ViolationRecord`/`RestrictedRecord` remain the row-level typed contract for the API.

Output (written by `margadrishti.ingestion.run`):
  bronze/violations.parquet   — analytics-safe columns only
  _restricted/violations_pii.parquet — PII, access-controlled, joined by record_id only

Source columns of note:
  violation_type   JSON array of strings   e.g. ["WRONG PARKING","NO PARKING"]
  offence_code     JSON array of ints       e.g. [112,104]
  created_datetime ISO w/ +00 offset (UTC)  e.g. 2023-11-20 00:28:46+00
  validation_status approved|rejected|NaN(→unvalidated)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pandas as pd

from margadrishti.core.config import get_settings
from margadrishti.core.schemas import ValidationStatus

# Analytics-safe vs PII column split — the boundary, declared once.
PII_COLUMNS = [
    "vehicle_number",
    "updated_vehicle_number",
    "vehicle_type",
    "updated_vehicle_type",
    "device_id",
    "created_by_id",
]


@dataclass(frozen=True)
class IngestResult:
    safe: pd.DataFrame        # analytics-safe
    restricted: pd.DataFrame  # PII (record_id-keyed)
    n_rows: int
    n_dropped: int            # rows dropped for invalid geometry/time


def _pseudonymise(series: pd.Series, salt: str) -> pd.Series:
    """Stable salted hash so enforcement-exposure features work without exposing identity."""
    def h(v: object) -> str | None:
        if pd.isna(v):
            return None
        return hashlib.sha256(f"{salt}:{v}".encode()).hexdigest()[:16]

    return series.map(h)


def _parse_json_array(series: pd.Series) -> pd.Series:
    def p(v: object) -> tuple:
        if pd.isna(v):
            return ()
        try:
            return tuple(json.loads(v))
        except (ValueError, TypeError):
            return ()

    return series.map(p)


def _norm_validation(series: pd.Series) -> pd.Series:
    m = {"approved": ValidationStatus.APPROVED, "rejected": ValidationStatus.REJECTED}
    return series.map(lambda v: (m.get(v, ValidationStatus.UNVALIDATED)).value)


def load_violations(csv_path: str) -> IngestResult:
    """Parse + validate + split PII. Pure (no IO side effects beyond reading csv_path)."""
    salt = get_settings().pii_salt
    df = pd.read_csv(csv_path, low_memory=False)

    n_raw = len(df)
    # Geometry + time validity (Bengaluru bbox guard against stray 0,0 / nulls).
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    ts = pd.to_datetime(df["created_datetime"], utc=True, errors="coerce")
    valid = (
        lat.between(12.6, 13.3) & lon.between(77.3, 77.9) & ts.notna()
    )

    safe = pd.DataFrame(
        {
            "record_id": df["id"],
            "lat": lat,
            "lon": lon,
            "location_text": df["location"],
            "violation_types": _parse_json_array(df["violation_type"]),
            "offence_codes": _parse_json_array(df["offence_code"]),
            "observed_at_utc": ts,
            "police_station": df["police_station"],
            "junction_name": df["junction_name"],
            "center_code": df["center_code"].astype("string"),
            "validation_status": _norm_validation(df["validation_status"]),
            "device_ref": _pseudonymise(df["device_id"], salt),
            "officer_ref": _pseudonymise(df["created_by_id"], salt),
        }
    ).loc[valid].reset_index(drop=True)

    restricted = pd.DataFrame(
        {"record_id": df["id"], **{c: df[c] for c in PII_COLUMNS}}
    ).loc[valid].reset_index(drop=True)

    return IngestResult(
        safe=safe, restricted=restricted, n_rows=len(safe), n_dropped=n_raw - int(valid.sum())
    )
