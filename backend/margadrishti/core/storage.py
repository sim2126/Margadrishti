"""Medallion storage access. Parquet/DuckDB is the reproducibility/CI tier; PostGIS is
the production serving store (see margadrishti.db.serving). The CI/offline tier never touches
network or Docker.

Layers: bronze (validated raw) → silver (cleaned, geo-resolved) → gold (features/serving).
Artifacts are content-addressed by a manifest so any ETL run is reproducible.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from margadrishti.core.config import Settings, get_settings


class Storage:
    """Thin layer over the medallion artifacts. Inject in tests; do not use globals."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        for layer in (self.s.bronze, self.s.silver, self.s.gold, self.s.restricted_root):
            layer.mkdir(parents=True, exist_ok=True)

    # --- Parquet (reproducible / offline) ---------------------------------
    def write_parquet(self, df: pd.DataFrame, layer: Path, name: str) -> Path:
        path = layer / f"{name}.parquet"
        df.to_parquet(path, index=False)
        return path

    def read_parquet(self, layer: Path, name: str) -> pd.DataFrame:
        return pd.read_parquet(layer / f"{name}.parquet")

    def _query_internal(self, sql: str) -> pd.DataFrame:
        """Run analytical SQL over gold parquet via DuckDB (no server needed).

        INTERNAL ONLY. This accepts arbitrary SQL and MUST NOT be reachable from the
        copilot or any user input. Copilot/API access goes through typed repository
        methods + parameterised queries over allowlisted views (see api/services).
        """
        con = duckdb.connect()
        try:
            con.execute(f"SET file_search_path='{self.s.gold.as_posix()}'")
            return con.execute(sql).df()
        finally:
            con.close()

    # PostGIS publishing lives ONLY in margadrishti.db.serving.publish_all (TRUNCATE+INSERT into
    # pre-created tables, preserving indexes/grants/RLS and the tiles_cii view). ETL/train
    # jobs write Parquet artifacts only and never touch the serving store directly.
