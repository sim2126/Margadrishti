"""Content-addressed versioning + RFC 3339 timestamps. Every artifact and provenance
record is traceable to the exact data, road network, feature schema and code that
produced it (CLAUDE.md: jobs are versioned; copilot tools are provenance-bearing).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

# Bump when the feature contract changes (PANEL_FEATURES / aggregation semantics).
FEATURE_VERSION = "panel-v1"
# Bump when CII component set / weighting semantics change.
CII_VERSION = "cii-v2"


def now_rfc3339() -> str:
    """RFC 3339 / ISO 8601 UTC, e.g. 2026-06-22T10:11:12.345678+00:00."""
    return datetime.now(timezone.utc).isoformat()


def as_of_rfc3339(horizon) -> str:
    """Format a data-horizon date marker as RFC 3339 UTC, e.g. 2024-04-08T00:00:00Z.
    `horizon` may be a pandas Timestamp / datetime / date / string."""
    import pandas as pd

    ts = pd.Timestamp(horizon)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def file_fingerprint(path: Path | str) -> str:
    """Cheap stable content version: size + mtime + first/last 64KB hash."""
    path = Path(path)
    if not path.exists() or path.is_dir():
        return "missing"
    st = path.stat()
    h = hashlib.sha256()
    h.update(f"{st.st_size}:{int(st.st_mtime)}".encode())
    with path.open("rb") as f:
        h.update(f.read(65536))
        if st.st_size > 65536:
            f.seek(-65536, 2)
            h.update(f.read(65536))
    return h.hexdigest()[:16]


def road_network_version(graph_cache: Path | str, bbox: tuple | None) -> str:
    """Identifies the OSM graph: cache fingerprint + the bbox it was built for."""
    fp = file_fingerprint(graph_cache)
    bb = "x".join(f"{c:.4f}" for c in bbox) if bbox else "auto"
    return f"osm-{fp}-{bb}"
