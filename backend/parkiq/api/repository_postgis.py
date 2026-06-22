"""PostGIS-backed repository — production serving tier. Mirrors GoldRepository's method
surface so services are storage-agnostic. Parameterised SQL only (no string interpolation
of inputs). Zone-scoped row-level security is applied per connection via a session GUC,
so jurisdiction enforcement happens in the database, not just the application.
"""

from __future__ import annotations

import json

import pandas as pd

from parkiq.api.repository import NON_DEPLOYABLE_ZONES
from parkiq.core.config import Settings, get_settings


class PostgisRepository:
    def __init__(self, settings: Settings | None = None, zone_scope: list[str] | None = None) -> None:
        from sqlalchemy import create_engine

        self.s = settings or get_settings()
        self.zone_scope = zone_scope
        # Reader prefers the non-owner DSN so RLS binds; pooling tuned for a long-lived
        # API process (pre_ping avoids stale connections, recycle survives DB restarts).
        dsn = self.s.postgis_read_dsn or self.s.postgis_dsn
        self._engine = create_engine(
            dsn, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600
        )

    def _q(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            # RLS: bind the officer's jurisdictions for this read (command role = unset).
            if self.zone_scope is not None:
                conn.execute(
                    text("SELECT set_config('parkiq.zone_scope', :z, true)"),
                    {"z": ",".join(self.zone_scope)},
                )
            return pd.read_sql(text(sql), conn, params=params or {})

    def cii_segments(self, limit: int = 2000, zone: str | None = None) -> pd.DataFrame:
        where = "WHERE d.zone = :zone" if zone else ""
        return self._q(
            f"""
            SELECT c.physical_id, c.name, c.highway, c.cii, c.cii_risk_is_interim_biased,
                   c.observed_count, c.approved_count, c.approval_rate,
                   c.cii_component__risk, c.cii_component__centrality, c.cii_component__obstruction,
                   d.centroid_lat, d.centroid_lon, ST_AsText(d.geom) AS geometry_wkt,
                   d.zone, d.junction, d.betweenness
            FROM cii c JOIN segments_dim d USING (physical_id)
            {where}
            ORDER BY c.cii DESC LIMIT :limit
            """,
            {"zone": zone, "limit": limit},
        )

    def segment_detail(self, physical_id: str) -> dict | None:
        df = self._q(
            """
            SELECT c.*, d.centroid_lat, d.centroid_lon, ST_AsText(d.geom) AS geometry_wkt,
                   d.zone, d.junction, f.n_officers, f.n_devices, f.active_hours,
                   f.mean_match_confidence, p.risk AS predicted_risk, p.model_version, p.as_of
            FROM cii c JOIN segments_dim d USING (physical_id)
            LEFT JOIN segment_features f USING (physical_id)
            LEFT JOIN predictions p USING (physical_id)
            WHERE c.physical_id = :pid
            """,
            {"pid": physical_id},
        )
        return None if df.empty else df.iloc[0].to_dict()

    def hour_of_week(self, physical_id: str) -> pd.DataFrame:
        return self._q(
            "SELECT hour_of_week, count FROM segment_hour_of_week "
            "WHERE physical_id = :pid ORDER BY hour_of_week",
            {"pid": physical_id},
        )

    def forecast(self, limit: int = 50, zone: str | None = None) -> pd.DataFrame:
        where = "WHERE d.zone = :zone" if zone else ""
        return self._q(
            f"""
            SELECT p.physical_id, d.name, d.zone, d.junction, d.centroid_lat, d.centroid_lon,
                   p.risk, p.model_version, p.as_of, c.cii
            FROM predictions p JOIN segments_dim d USING (physical_id)
            LEFT JOIN cii c USING (physical_id)
            {where}
            ORDER BY p.risk DESC LIMIT :limit
            """,
            {"zone": zone, "limit": limit},
        )

    def zone_trends(self) -> pd.DataFrame:
        return self._q(
            """
            SELECT d.zone, COUNT(*) AS n_segments, SUM(c.observed_count) AS observed_count,
                   AVG(c.cii) AS mean_cii
            FROM cii c JOIN segments_dim d USING (physical_id)
            GROUP BY d.zone ORDER BY observed_count DESC
            """
        )

    def segments_in_zone(self, zone: str, limit: int = 200) -> pd.DataFrame:
        return self._q(
            """
            SELECT c.physical_id, c.name, c.cii, c.observed_count,
                   d.centroid_lat, d.centroid_lon, d.junction, p.risk
            FROM cii c JOIN segments_dim d USING (physical_id)
            LEFT JOIN predictions p USING (physical_id)
            WHERE d.zone = :zone ORDER BY c.cii DESC LIMIT :limit
            """,
            {"zone": zone, "limit": limit},
        )

    def zones(self) -> list[str]:
        df = self._q("SELECT DISTINCT zone FROM segments_dim WHERE zone IS NOT NULL ORDER BY zone")
        return df["zone"].tolist()

    def deployable_zones(self) -> list[str]:
        return [z for z in self.zones() if z not in NON_DEPLOYABLE_ZONES]

    def manifest(self) -> dict:
        """Provenance source of truth — the versioned manifest written by ETL/train."""
        path = self.s.gold / "manifest.json"
        if not path.exists():
            return {"etl": {}, "model": {}}
        return json.loads(path.read_text(encoding="utf-8"))
