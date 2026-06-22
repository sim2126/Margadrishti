"""Central typed configuration. The ONLY place env vars are read.

Per CLAUDE.md: model IDs are env vars, never hard-coded; offline mode must work
without Docker or network so the reproducibility/CI tier needs no external services.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Claude copilot. Per CLAUDE.md, model IDs come from env; defaults are permitted
    # in EXACTLY ONE place — here — and nowhere else in the codebase. Business logic
    # must read these settings, never embed a literal model id.
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    claude_model_reasoning: str = Field(default="claude-opus-4-8", alias="CLAUDE_MODEL_REASONING")
    claude_model_fast: str = Field(default="claude-sonnet-4-6", alias="CLAUDE_MODEL_FAST")
    # The copilot endpoint is currently unauthenticated. Default OFF so it cannot spend
    # the API key from the open internet; enable only behind auth + rate limiting.
    copilot_llm_enabled: bool = Field(default=False, alias="PARKIQ_COPILOT_LLM_ENABLED")

    # Serving store + queue/broker. The writer (worker/publish) uses POSTGIS_DSN (owner,
    # bypasses RLS to load tables). The API/reader should use POSTGIS_READ_DSN — a
    # non-owner login role — so zone-scoped row-level security actually binds. Falls back
    # to POSTGIS_DSN if unset (RLS then bypassed; flagged as a hardening gap).
    postgis_dsn: str = Field(default="", alias="POSTGIS_DSN")
    postgis_read_dsn: str = Field(default="", alias="POSTGIS_READ_DSN")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Storage roots
    data_root: Path = Field(default=Path("./data"), alias="PARKIQ_DATA_ROOT")
    restricted_root: Path = Field(default=Path("./data/_restricted"), alias="PARKIQ_RESTRICTED_ROOT")

    # Raw inputs
    raw_violations_csv: Path = Field(default=Path(""), alias="RAW_VIOLATIONS_CSV")
    raw_events_csv: Path = Field(default=Path(""), alias="RAW_EVENTS_CSV")

    # Geo / time
    bbox: str = Field(default="Bengaluru, Karnataka, India", alias="PARKIQ_BBOX")
    # Optional ETL extent "west,south,east,north". Bounds the OSM download/run when no
    # --bbox is passed (e.g. the compose bootstrap). Empty = derive from the data (full city).
    etl_bbox: str = Field(default="", alias="PARKIQ_ETL_BBOX")
    tz: str = Field(default="Asia/Kolkata", alias="PARKIQ_TZ")
    h3_resolution: int = Field(default=10, alias="H3_RESOLUTION")

    # Modes
    offline: bool = Field(default=True, alias="PARKIQ_OFFLINE")
    seed: int = Field(default=42, alias="PARKIQ_SEED")

    # Pseudonymisation salt for device/officer ids (set a real secret in prod).
    pii_salt: str = Field(default="parkiq-dev-salt-change-me", alias="PARKIQ_PII_SALT")

    def require_raw_violations(self) -> Path:
        """Fail fast with an actionable message if the raw CSV is missing/empty.
        A clean shell with no .env must not silently produce empty artifacts."""
        p = self.raw_violations_csv
        if not p or str(p) in ("", ".") or not p.exists():
            raise SystemExit(
                "ParkIQ: RAW_VIOLATIONS_CSV is not set or does not resolve "
                f"(got {p!r}). Copy .env.example to .env and set RAW_VIOLATIONS_CSV "
                "to the violations CSV path, or pass it via the environment."
            )
        if p.stat().st_size == 0:
            raise SystemExit(f"ParkIQ: raw violations CSV is empty: {p}")
        return p

    # Medallion layer paths -------------------------------------------------
    @property
    def bronze(self) -> Path:
        return self.data_root / "bronze"

    @property
    def silver(self) -> Path:
        return self.data_root / "silver"

    @property
    def gold(self) -> Path:
        return self.data_root / "gold"


@lru_cache
def get_settings() -> Settings:
    return Settings()
