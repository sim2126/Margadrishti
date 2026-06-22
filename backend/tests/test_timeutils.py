"""Foundational test: the UTC→IST contract must hold (CLAUDE.md timezone rule)."""

from datetime import datetime, timezone

from parkiq.core.timeutils import hour_of_week_ist, ist_calendar_features, to_ist


def test_utc_to_ist_offset():
    # 2024-01-01 20:00 UTC == 2024-01-02 01:30 IST (next day, +5h30)
    dt = datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc)
    ist = to_ist(dt)
    assert (ist.hour, ist.minute) == (1, 30)
    assert ist.day == 2


def test_hour_of_week_uses_ist_not_utc():
    dt = datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc)  # Mon UTC → Tue 01:30 IST
    feats = ist_calendar_features(dt)
    assert feats["hour"] == 1            # NOT 20 — proves IST derivation
    assert feats["dow"] == 1             # Tuesday
    assert hour_of_week_ist(dt) == 1 * 24 + 1
