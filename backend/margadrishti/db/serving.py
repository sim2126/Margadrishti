"""Publish the gold layer into PostGIS for production serving.

Idempotent and non-destructive: data lands in a staging table, then a transactional
TRUNCATE+INSERT swaps it into the live table — indexes, GIST, grants and RLS policies
survive (never DROP the live table). geometry is rebuilt from WKT into a real
geometry(LineString,4326) column so Martin can tile it.

    python -m margadrishti.db.serving        # apply schema + publish all gold tables
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pandas as pd

from margadrishti.core.config import Settings, get_settings

# Plain tables: (gold parquet name, target table). segments_dim is handled specially
# because it needs geometry construction from WKT.
PLAIN_TABLES = [
    ("cii", "cii"),
    ("predictions", "predictions"),
    ("segment_features", "segment_features"),
    ("segment_hour_of_week", "segment_hour_of_week"),
]

# Columns that MUST be present in the parquet before we truncate the live table, and the
# primary-key column to check for uniqueness (None = no uniqueness requirement).
REQUIRED = {
    "segments_dim": (["physical_id", "geometry_wkt", "zone"], "physical_id"),
    "cii": (["physical_id", "cii"], "physical_id"),
    "predictions": (["physical_id", "risk"], "physical_id"),
    "segment_features": (["physical_id"], "physical_id"),
    "segment_hour_of_week": (["physical_id", "hour_of_week", "count"], None),
}
# Stable 63-bit key for the publish advisory lock (serialises concurrent publishers).
_PUBLISH_LOCK_KEY = 0x50524B49


def _validate(df: pd.DataFrame, table: str) -> None:
    required, pk = REQUIRED[table]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"{table}.parquet missing required columns {missing}")
    if pk and df[pk].duplicated().any():
        raise RuntimeError(f"{table}.parquet has duplicate {pk} values; refusing to publish")


def _engine(settings: Settings):
    from sqlalchemy import create_engine

    if not settings.postgis_dsn:
        raise SystemExit("POSTGIS_DSN is not set; cannot publish to serving store.")
    return create_engine(settings.postgis_dsn)


def _apply_schema(conn) -> None:
    from sqlalchemy import text

    sql = (resources.files("margadrishti.db") / "schema.sql").read_text(encoding="utf-8")
    for stmt in _split_sql(sql):
        conn.execute(text(stmt))


def _split_sql(sql: str) -> list[str]:
    """Split into executable statements on ';', keeping dollar-quoted blocks
    (DO $$ ... $$) intact. Full-line comments are stripped first so a leading comment
    never swallows the statement that follows it."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    out, buf, in_dollar = [], [], False
    for line in lines:
        if line.count("$$") % 2:
            in_dollar = not in_dollar
        buf.append(line)
        if line.rstrip().endswith(";") and not in_dollar:
            stmt = "\n".join(buf).strip()
            if stmt:
                out.append(stmt.rstrip(";"))
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append(tail.rstrip(";"))
    return out


def _table_columns(conn, table: str) -> set[str]:
    from sqlalchemy import text

    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": table},
    )
    return {r[0] for r in rows}


def _swap_plain(conn, df: pd.DataFrame, table: str) -> None:
    """Load only the columns the target table actually declares. Gold parquet may carry
    extra analytical columns (e.g. cii.h3_cells, segment_features.weighted_count) that
    live elsewhere in the serving schema — silently dropping them here is intentional."""
    from sqlalchemy import text

    _validate(df, table)
    use = [c for c in df.columns if c in _table_columns(conn, table)]
    if not use:
        raise RuntimeError(f"no overlapping columns between {table}.parquet and table {table}")
    df[use].to_sql(f"{table}__staging", conn, if_exists="replace", index=False)
    conn.execute(text(f'TRUNCATE TABLE "{table}"'))
    cols = ", ".join(f'"{c}"' for c in use)
    conn.execute(text(f'INSERT INTO "{table}" ({cols}) SELECT {cols} FROM "{table}__staging"'))
    conn.execute(text(f'DROP TABLE "{table}__staging"'))


def _swap_segments_dim(conn, df: pd.DataFrame) -> None:
    from sqlalchemy import text

    _validate(df, "segments_dim")
    stage = df.copy()
    # h3_cells (list) → postgres text[]; geometry built from WKT in SQL below.
    stage["h3_cells"] = stage["h3_cells"].apply(lambda xs: "{" + ",".join(map(str, xs)) + "}")
    stage.to_sql("segments_dim__staging", conn, if_exists="replace", index=False)
    conn.execute(text("TRUNCATE TABLE segments_dim"))
    conn.execute(
        text(
            """
            INSERT INTO segments_dim
                (physical_id, name, highway, zone, junction, length, betweenness,
                 obstruction_weight, centroid_lat, centroid_lon, h3_cells, geom)
            SELECT physical_id, name, highway, zone, junction, length, betweenness,
                   obstruction_weight, centroid_lat, centroid_lon,
                   h3_cells::text[],
                   ST_SetSRID(ST_GeomFromText(geometry_wkt), 4326)
            FROM segments_dim__staging
            """
        )
    )
    conn.execute(text("DROP TABLE segments_dim__staging"))


def publish_all(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    gold = s.gold
    engine = _engine(s)
    with engine.begin() as conn:
        from sqlalchemy import text

        # Serialise concurrent publishers (staging table names are shared).
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PUBLISH_LOCK_KEY})
        _apply_schema(conn)
        _swap_segments_dim(conn, pd.read_parquet(gold / "segments_dim.parquet"))
        published = ["segments_dim"]
        for name, table in PLAIN_TABLES:
            path = Path(gold / f"{name}.parquet")
            if path.exists():
                _swap_plain(conn, pd.read_parquet(path), table)
                published.append(table)
    print(f"OK published to PostGIS: {', '.join(published)}")
    return {"published": published}


if __name__ == "__main__":
    publish_all()
