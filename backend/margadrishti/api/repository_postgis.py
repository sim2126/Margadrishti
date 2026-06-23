"""PostGIS-backed repository — production serving tier. Mirrors GoldRepository's method
surface so services are storage-agnostic. Parameterised SQL only (no string interpolation
of inputs). Zone-scoped row-level security is applied per connection via a session GUC,
so jurisdiction enforcement happens in the database, not just the application.
"""

from __future__ import annotations

import json

import pandas as pd

from margadrishti.api.repository import NON_DEPLOYABLE_ZONES
from margadrishti.core.config import Settings, get_settings


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
                    text("SELECT set_config('margadrishti.zone_scope', :z, true)"),
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

    def cii_with_risk(self, limit: int = 2000, zone: str | None = None) -> pd.DataFrame:
        """CII ⋈ geometry ⋈ predicted risk — area selection needs risk + priority utility."""
        where = "WHERE d.zone = :zone" if zone else ""
        return self._q(
            f"""
            SELECT c.physical_id, c.name, c.highway, c.cii, c.cii_risk_is_interim_biased,
                   c.observed_count, c.approval_rate,
                   d.centroid_lat, d.centroid_lon, d.zone, d.junction,
                   p.risk AS predicted_risk
            FROM cii c JOIN segments_dim d USING (physical_id)
            LEFT JOIN predictions p USING (physical_id)
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

    def hourly_observed(
        self,
        hour: int | None = None,
        day_of_week: int | None = None,
        zone: str | None = None,
        limit: int = 2000,
    ) -> pd.DataFrame:
        """Observed-enforcement counts in an IST time window (see GoldRepository.hourly_observed)."""
        params: dict = {"limit": limit}
        preds: list[str] = []
        if day_of_week is not None and hour is not None:
            preds.append("hour_of_week = :how_eq")
            params["how_eq"] = day_of_week * 24 + hour
        elif hour is not None:
            preds.append("(hour_of_week % 24) = :hod")
            params["hod"] = hour
        elif day_of_week is not None:
            preds.append("hour_of_week >= :dlo AND hour_of_week < :dhi")
            params["dlo"] = day_of_week * 24
            params["dhi"] = day_of_week * 24 + 24
        win_where = ("WHERE " + " AND ".join(preds)) if preds else ""
        zone_where = "WHERE d.zone = :zone" if zone else ""
        if zone:
            params["zone"] = zone
        return self._q(
            f"""
            WITH win AS (
                SELECT physical_id, SUM(count) AS window_count
                FROM segment_hour_of_week {win_where} GROUP BY physical_id
            )
            SELECT c.physical_id, c.name, c.highway, c.cii, c.cii_risk_is_interim_biased,
                   c.observed_count, c.approval_rate,
                   d.centroid_lat, d.centroid_lon, d.zone, d.junction,
                   COALESCE(w.window_count, 0) AS window_count
            FROM cii c JOIN segments_dim d USING (physical_id)
            LEFT JOIN win w USING (physical_id)
            {zone_where}
            ORDER BY window_count DESC, c.cii DESC LIMIT :limit
            """,
            params,
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

    def all_segments(self, zone: str | None = None) -> pd.DataFrame:
        where = "WHERE zone = :zone" if zone else ""
        return self._q(
            f"""SELECT physical_id, name, junction, highway, zone, betweenness,
                       centroid_lat, centroid_lon FROM segments_dim {where}""",
            {"zone": zone} if zone else {},
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

    def eval_report(self) -> dict:
        """Model evaluation artifact written by the training pipeline."""
        path = self.s.gold / "eval_report.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
