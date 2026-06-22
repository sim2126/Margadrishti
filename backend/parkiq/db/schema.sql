-- ParkIQ production serving schema (PostGIS). Idempotent: safe to re-run.
-- Tables are populated by parkiq.db.serving.publish_all from the gold layer.
-- Zone access is enforced here (row-level security), not only in the application.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Segment dimension: geometry + zone/junction + static attributes.
CREATE TABLE IF NOT EXISTS segments_dim (
    physical_id        TEXT PRIMARY KEY,
    name               TEXT,
    highway            TEXT,
    zone               TEXT,
    junction           TEXT,
    length             DOUBLE PRECISION,
    betweenness        DOUBLE PRECISION,
    obstruction_weight DOUBLE PRECISION,
    centroid_lat       DOUBLE PRECISION,
    centroid_lon       DOUBLE PRECISION,
    h3_cells           TEXT[],
    geom               geometry(LineString, 4326)
);
CREATE INDEX IF NOT EXISTS segments_dim_geom_gix ON segments_dim USING GIST (geom);
CREATE INDEX IF NOT EXISTS segments_dim_zone_ix  ON segments_dim (zone);

CREATE TABLE IF NOT EXISTS cii (
    physical_id                   TEXT PRIMARY KEY,
    name                          TEXT,
    highway                       TEXT,
    cii                           DOUBLE PRECISION,
    cii_risk_is_interim_biased    BOOLEAN,
    observed_count                INTEGER,
    approved_count                DOUBLE PRECISION,
    approval_rate                 DOUBLE PRECISION,
    cii_component__risk           DOUBLE PRECISION,
    cii_component__centrality     DOUBLE PRECISION,
    cii_component__obstruction    DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS cii_score_ix ON cii (cii DESC);

CREATE TABLE IF NOT EXISTS predictions (
    physical_id   TEXT PRIMARY KEY,
    risk          DOUBLE PRECISION,
    model_version TEXT,
    as_of         TEXT
);

CREATE TABLE IF NOT EXISTS segment_features (
    physical_id            TEXT PRIMARY KEY,
    observed_count         INTEGER,
    approved_count         DOUBLE PRECISION,
    approval_rate          DOUBLE PRECISION,
    n_officers             INTEGER,
    n_devices              INTEGER,
    active_hours           INTEGER,
    mean_match_confidence  DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS segment_hour_of_week (
    physical_id   TEXT,
    hour_of_week  INTEGER,
    count         INTEGER
);
CREATE INDEX IF NOT EXISTS show_pid_ix ON segment_hour_of_week (physical_id);

-- Tiles view for Martin: geometry + score + operational label fields.
-- security_invoker=true → the view runs with the QUERYING role's privileges/RLS, not the
-- owner's, so it cannot be used to bypass zone isolation (PG15+).
CREATE OR REPLACE VIEW tiles_cii WITH (security_invoker = true) AS
SELECT d.physical_id, d.name, d.junction, d.zone, d.geom,
       c.cii, c.observed_count, c.cii_component__risk,
       c.cii_component__centrality, c.cii_component__obstruction
FROM segments_dim d
JOIN cii c USING (physical_id);

-- Row-level security: a session sets parkiq.zone_scope to the officer's jurisdictions
-- (comma-separated). NULL/unset = unrestricted (command role). Applied on the dimension;
-- joined reads inherit the restriction.
ALTER TABLE segments_dim ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS zone_scope ON segments_dim;
CREATE POLICY zone_scope ON segments_dim
    USING (
        current_setting('parkiq.zone_scope', true) IS NULL
        OR current_setting('parkiq.zone_scope', true) = ''
        OR zone = ANY (string_to_array(current_setting('parkiq.zone_scope', true), ','))
    );

-- Read-only serving role used by the API (LOGIN, non-owner → RLS BINDS for it; the
-- owner that runs publish bypasses RLS and can load tables). The password here is a
-- dev/compose default — ROTATE in any real deployment and inject via secrets.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'parkiq_api') THEN
        CREATE ROLE parkiq_api LOGIN PASSWORD 'parkiq_api';
    END IF;
END $$;
GRANT SELECT ON segments_dim, cii, predictions, segment_features, segment_hour_of_week, tiles_cii
    TO parkiq_api;
