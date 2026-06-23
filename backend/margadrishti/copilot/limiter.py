"""In-memory spend guard for the live copilot.

Two caps, both enforced server-side (a client-side counter is trivially bypassable):
- per-session: a UX limit for one visitor (keyed by an X-Session-Id header, IP fallback).
- per-day: the hard global ceiling across everyone — this is what actually bounds spend.

State is per-process and resets at UTC midnight. Fine for the single-instance offline/gold
demo deployment; a multi-instance production rollout would move counters to Redis.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone


class CopilotLimiter:
    def __init__(self, max_per_session: int, max_per_day: int) -> None:
        self.max_per_session = max_per_session
        self.max_per_day = max_per_day
        self._lock = threading.Lock()
        self._day = self._today()
        self._day_count = 0
        self._session_counts: dict[str, int] = {}

    @staticmethod
    def _today():
        return datetime.now(timezone.utc).date()

    def _roll_if_new_day(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._day_count = 0
            self._session_counts.clear()

    def try_consume(self, session_id: str) -> tuple[bool, str | None]:
        """Consume one live-call unit. Returns (allowed, reason) — reason is "day" or
        "session" when denied, else None. Denied calls consume nothing."""
        with self._lock:
            self._roll_if_new_day()
            if self._day_count >= self.max_per_day:
                return False, "day"
            if self._session_counts.get(session_id, 0) >= self.max_per_session:
                return False, "session"
            self._session_counts[session_id] = self._session_counts.get(session_id, 0) + 1
            self._day_count += 1
            return True, None
