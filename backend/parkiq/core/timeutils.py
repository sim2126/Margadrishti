"""Timezone discipline (contractual, per CLAUDE.md).

Storage is UTC. Every operational feature (hour-of-day, day-of-week, hour-of-week)
is derived in Asia/Kolkata. Never read hour-of-day directly off the UTC value — the
5h30 offset would silently corrupt every temporal pattern the model learns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def to_utc(dt: datetime) -> datetime:
    """Normalise any datetime to tz-aware UTC."""
    if dt.tzinfo is None:
        raise ValueError("Refusing to assume tz for a naive datetime; make it explicit.")
    return dt.astimezone(timezone.utc)


def to_ist(dt_utc: datetime) -> datetime:
    return to_utc(dt_utc).astimezone(IST)


def hour_of_week_ist(dt_utc: datetime) -> int:
    """0–167 operational bucket in IST (Mon 00:00 = 0)."""
    ist = to_ist(dt_utc)
    return ist.weekday() * 24 + ist.hour


def ist_calendar_features(dt_utc: datetime) -> dict[str, int]:
    ist = to_ist(dt_utc)
    return {
        "hour": ist.hour,
        "dow": ist.weekday(),
        "hour_of_week": ist.weekday() * 24 + ist.hour,
        "is_weekend": int(ist.weekday() >= 5),
    }
