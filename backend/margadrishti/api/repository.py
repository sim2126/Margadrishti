"""Read-only repository over the gold layer. Parameterised DuckDB queries against an
allowlisted set of parquet artifacts (offline) — the ONLY data path the API/copilot use.
No arbitrary SQL, no string-interpolated user input. The PostGIS-backed implementation
would swap the FROM targets for tables/views with the same method surface.
"""

from __future__ import annotations

import json
from functools import cached_property

import duckdb
import pandas as pd

from margadrishti.core.config import Settings, get_settings

# Zone labels that are data sentinels, not commandable jurisdictions. Kept in analytics
# (zone_trends) but never offered as a deployment target.
NON_DEPLOYABLE_ZONES = {"No Police Station", "Unknown", None, ""}


class GoldRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()

    @cached_property
    def _paths(self) -> dict[str, str]:
        g = self.s.gold
        return {
            "cii": (g / "cii.parquet").as_posix(),
            "dim": (g / "segments_dim.parquet").as_posix(),
            "feats": (g / "segment_features.parquet").as_posix(),
            "preds": (g / "predictions.parquet").as_posix(),
            "how": (g / "segment_hour_of_week.parquet").as_posix(),
        }

    def _q(self, sql: str, params: list | None = None) -> pd.DataFrame:
        con = duckdb.connect()
        try:
            return con.execute(sql, params or []).df()
        finally:
            con.close()

    # --- CII / map ---------------------------------------------------------
    def cii_segments(self, limit: int = 2000, zone: str | None = None) -> pd.DataFrame:
        """CII joined to geometry/centroid/zone — the heatmap + ranking source."""
        where = "WHERE d.zone = ?" if zone else ""
        params = [zone, limit] if zone else [limit]
        return self._q(
            f"""
            SELECT c.physical_id, c.name, c.highway, c.cii,
                   c.cii_risk_is_interim_biased,
                   c.observed_count, c.approved_count, c.approval_rate,
                   c.cii_component__risk, c.cii_component__centrality,
                   c.cii_component__obstruction,
                   d.centroid_lat, d.centroid_lon, d.geometry_wkt, d.zone, d.junction,
                   d.betweenness
            FROM read_parquet('{self._paths["cii"]}') c
            JOIN read_parquet('{self._paths["dim"]}') d USING (physical_id)
            {where}
            ORDER BY c.cii DESC
            LIMIT ?
            """,
            params,
        )

    def cii_with_risk(self, limit: int = 2000, zone: str | None = None) -> pd.DataFrame:
        """CII ⋈ geometry ⋈ predicted risk — area selection needs risk + priority utility."""
        where = "WHERE d.zone = ?" if zone else ""
        params = [zone, limit] if zone else [limit]
        return self._q(
            f"""
            SELECT c.physical_id, c.name, c.highway, c.cii, c.cii_risk_is_interim_biased,
                   c.observed_count, c.approval_rate,
                   d.centroid_lat, d.centroid_lon, d.zone, d.junction,
                   p.risk AS predicted_risk
            FROM read_parquet('{self._paths["cii"]}') c
            JOIN read_parquet('{self._paths["dim"]}') d USING (physical_id)
            LEFT JOIN read_parquet('{self._paths["preds"]}') p USING (physical_id)
            {where}
            ORDER BY c.cii DESC
            LIMIT ?
            """,
            params,
        )

    def segment_detail(self, physical_id: str) -> dict | None:
        df = self._q(
            f"""
            SELECT c.*, d.centroid_lat, d.centroid_lon, d.geometry_wkt, d.zone, d.junction,
                   f.n_officers, f.n_devices, f.active_hours, f.mean_match_confidence,
                   f.first_seen_utc, f.last_seen_utc,
                   p.risk AS predicted_risk, p.model_version, p.as_of
            FROM read_parquet('{self._paths["cii"]}') c
            JOIN read_parquet('{self._paths["dim"]}') d USING (physical_id)
            LEFT JOIN read_parquet('{self._paths["feats"]}') f USING (physical_id)
            LEFT JOIN read_parquet('{self._paths["preds"]}') p USING (physical_id)
            WHERE c.physical_id = ?
            """,
            [physical_id],
        )
        return None if df.empty else df.iloc[0].to_dict()

    def hour_of_week(self, physical_id: str) -> pd.DataFrame:
        return self._q(
            f"""SELECT hour_of_week, count FROM read_parquet('{self._paths["how"]}')
                WHERE physical_id = ? ORDER BY hour_of_week""",
            [physical_id],
        )

    def hourly_observed(
        self,
        hour: int | None = None,
        day_of_week: int | None = None,
        zone: str | None = None,
        limit: int = 2000,
    ) -> pd.DataFrame:
        """Observed-enforcement counts in an IST time window, per segment, joined to CII/geometry.

        hour_of_week = weekday*24 + hour (IST), so an hour-of-day slice sums that hour across
        all weekdays; a day_of_week+hour slice picks one cell. This is OBSERVED ENFORCEMENT,
        not prevalence, and not a per-hour CII — callers must keep that label.
        """
        preds: list[str] = []
        params: list = []
        if day_of_week is not None and hour is not None:
            preds.append("hour_of_week = ?")
            params.append(day_of_week * 24 + hour)
        elif hour is not None:
            preds.append("(hour_of_week % 24) = ?")
            params.append(hour)
        elif day_of_week is not None:
            preds.append("hour_of_week >= ? AND hour_of_week < ?")
            params += [day_of_week * 24, day_of_week * 24 + 24]
        win_where = ("WHERE " + " AND ".join(preds)) if preds else ""
        zone_where = "WHERE d.zone = ?" if zone else ""
        params += ([zone] if zone else []) + [limit]
        return self._q(
            f"""
            WITH win AS (
                SELECT physical_id, SUM(count) AS window_count
                FROM read_parquet('{self._paths["how"]}')
                {win_where}
                GROUP BY physical_id
            )
            SELECT c.physical_id, c.name, c.highway, c.cii, c.cii_risk_is_interim_biased,
                   c.observed_count, c.approval_rate,
                   d.centroid_lat, d.centroid_lon, d.zone, d.junction,
                   COALESCE(w.window_count, 0) AS window_count
            FROM read_parquet('{self._paths["cii"]}') c
            JOIN read_parquet('{self._paths["dim"]}') d USING (physical_id)
            LEFT JOIN win w USING (physical_id)
            {zone_where}
            ORDER BY window_count DESC, c.cii DESC
            LIMIT ?
            """,
            params,
        )

    # --- forecast / analytics ---------------------------------------------
    def forecast(self, limit: int = 50, zone: str | None = None) -> pd.DataFrame:
        where = "WHERE d.zone = ?" if zone else ""
        params = [zone, limit] if zone else [limit]
        return self._q(
            f"""
            SELECT p.physical_id, d.name, d.zone, d.junction, d.centroid_lat, d.centroid_lon,
                   p.risk, p.model_version, p.as_of, c.cii
            FROM read_parquet('{self._paths["preds"]}') p
            JOIN read_parquet('{self._paths["dim"]}') d USING (physical_id)
            LEFT JOIN read_parquet('{self._paths["cii"]}') c USING (physical_id)
            {where}
            ORDER BY p.risk DESC
            LIMIT ?
            """,
            params,
        )

    def zone_trends(self) -> pd.DataFrame:
        """Observed-enforcement-density by zone (NEVER 'prevalence')."""
        return self._q(
            f"""
            SELECT d.zone,
                   COUNT(*) AS n_segments,
                   SUM(c.observed_count) AS observed_count,
                   AVG(c.cii) AS mean_cii
            FROM read_parquet('{self._paths["cii"]}') c
            JOIN read_parquet('{self._paths["dim"]}') d USING (physical_id)
            GROUP BY d.zone ORDER BY observed_count DESC
            """
        )

    def segments_in_zone(self, zone: str, limit: int = 200) -> pd.DataFrame:
        """Risk-ranked segments with coordinates — input to the deployment optimiser."""
        return self._q(
            f"""
            SELECT c.physical_id, c.name, c.cii, c.observed_count,
                   d.centroid_lat, d.centroid_lon, d.junction, p.risk
            FROM read_parquet('{self._paths["cii"]}') c
            JOIN read_parquet('{self._paths["dim"]}') d USING (physical_id)
            LEFT JOIN read_parquet('{self._paths["preds"]}') p USING (physical_id)
            WHERE d.zone = ? ORDER BY c.cii DESC LIMIT ?
            """,
            [zone, limit],
        )

    def all_segments(self, zone: str | None = None) -> pd.DataFrame:
        """Full segment universe (road-graph nodes for neighbourhood/simulation).
        physical_id encodes the two endpoint nodes, so adjacency needs no extra artifact."""
        where = "WHERE zone = ?" if zone else ""
        return self._q(
            f"""SELECT physical_id, name, junction, highway, zone, betweenness,
                       centroid_lat, centroid_lon
                FROM read_parquet('{self._paths["dim"]}') {where}""",
            [zone] if zone else None,
        )

    def zones(self) -> list[str]:
        """All non-null zones present in the served data (analytics view — includes
        sentinel buckets like 'No Police Station')."""
        df = self._q(
            f"""SELECT DISTINCT zone FROM read_parquet('{self._paths["dim"]}')
                WHERE zone IS NOT NULL ORDER BY zone"""
        )
        return df["zone"].tolist()

    def deployable_zones(self) -> list[str]:
        """Zones that are real jurisdictions a unit can be tasked to — excludes sentinel
        buckets that have no commanding station."""
        return [z for z in self.zones() if z not in NON_DEPLOYABLE_ZONES]

    def manifest(self) -> dict:
        """Provenance source of truth (gold/manifest.json), with safe fallbacks."""
        path = self.s.gold / "manifest.json"
        if not path.exists():
            return {"etl": {}, "model": {}}
        return json.loads(path.read_text(encoding="utf-8"))
