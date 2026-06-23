"""Shared FastAPI dependencies. The repository tier is selected by config:
PostGIS for production serving, Parquet/DuckDB for the reproducibility/CI/offline tier.
Both implement the same method surface, so services are storage-agnostic.
"""

from __future__ import annotations

from functools import lru_cache

from margadrishti.api.repository import GoldRepository
from margadrishti.api.services import MargadrishtiService
from margadrishti.core.config import get_settings


def get_repository():
    s = get_settings()
    if not s.offline:
        if not s.postgis_read_dsn:
            raise RuntimeError(
                "MARGA_OFFLINE=false requires POSTGIS_READ_DSN for API serving. "
                "Refusing to silently fall back to the gold/Parquet tier in production mode."
            )
        from margadrishti.api.repository_postgis import PostgisRepository

        return PostgisRepository(s)
    return GoldRepository(s)


@lru_cache
def get_service() -> MargadrishtiService:
    return MargadrishtiService(repo=get_repository())
