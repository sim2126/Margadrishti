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
    copilot_llm_enabled: bool = Field(default=False, alias="MARGA_COPILOT_LLM_ENABLED")
    # Spend guards for the live copilot (only consulted when the LLM path is enabled).
    # Per-session = UX cap shown to one visitor; per-day = the hard global money ceiling
    # across everyone. On exceed, the copilot degrades to the deterministic fallback.
    copilot_max_per_session: int = Field(default=10, alias="MARGA_COPILOT_MAX_PER_SESSION")
    copilot_max_per_day: int = Field(default=200, alias="MARGA_COPILOT_MAX_PER_DAY")

    # Serving store + queue/broker. The writer (worker/publish) uses POSTGIS_DSN (owner,
    # bypasses RLS to load tables). The API/reader should use POSTGIS_READ_DSN — a
    # non-owner login role — so zone-scoped row-level security actually binds. Falls back
    # to POSTGIS_DSN if unset (RLS then bypassed; flagged as a hardening gap).
    postgis_dsn: str = Field(default="", alias="POSTGIS_DSN")
    postgis_read_dsn: str = Field(default="", alias="POSTGIS_READ_DSN")
    api_db_password: str = Field(default="", alias="MARGA_API_PASSWORD")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    # Comma-separated browser origins allowed to call the API. Use explicit origins in
    # production (e.g. the Cloudflare Pages URL). "*" is permitted only when set
    # intentionally for local/demo environments.
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="MARGA_CORS_ORIGINS",
    )

    # Storage roots
    data_root: Path = Field(default=Path("./data"), alias="MARGA_DATA_ROOT")
    restricted_root: Path = Field(default=Path("./data/_restricted"), alias="MARGA_RESTRICTED_ROOT")

    # Raw inputs
    raw_violations_csv: Path = Field(default=Path(""), alias="RAW_VIOLATIONS_CSV")
    raw_events_csv: Path = Field(default=Path(""), alias="RAW_EVENTS_CSV")

    # Geo / time
    bbox: str = Field(default="Bengaluru, Karnataka, India", alias="MARGA_BBOX")
    # Optional ETL extent "west,south,east,north". Bounds the OSM download/run when no
    # --bbox is passed (e.g. the compose bootstrap). Empty = derive from the data (full city).
    etl_bbox: str = Field(default="", alias="MARGA_ETL_BBOX")
    tz: str = Field(default="Asia/Kolkata", alias="MARGA_TZ")
    h3_resolution: int = Field(default=10, alias="H3_RESOLUTION")

    # Modes
    offline: bool = Field(default=True, alias="MARGA_OFFLINE")
    seed: int = Field(default=42, alias="MARGA_SEED")

    # Pseudonymisation salt for device/officer ids (set a real secret in prod).
    pii_salt: str = Field(default="margadrishti-dev-salt-change-me", alias="MARGA_PII_SALT")

    def require_raw_violations(self) -> Path:
        """Fail fast with an actionable message if the raw CSV is missing/empty.
        A clean shell with no .env must not silently produce empty artifacts."""
        p = self.raw_violations_csv
        if not p or str(p) in ("", ".") or not p.exists():
            raise SystemExit(
                "Margadrishti: RAW_VIOLATIONS_CSV is not set or does not resolve "
                f"(got {p!r}). Copy .env.example to .env and set RAW_VIOLATIONS_CSV "
                "to the violations CSV path, or pass it via the environment."
            )
        if p.stat().st_size == 0:
            raise SystemExit(f"Margadrishti: raw violations CSV is empty: {p}")
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

    @property
    def cors_allow_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
