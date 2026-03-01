-- ============================================================
-- FloodWatch Phase 4 — PostGIS Schema
-- Tables: flood_prediction, road_risk
-- ============================================================

-- Enable PostGIS extension (idempotent)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ────────────────────────────────────────────────────────────
-- flood_prediction: time-indexed flood polygons from LISFLOOD
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS flood_prediction (
    id              SERIAL PRIMARY KEY,
    geometry        GEOMETRY(Polygon, 4326) NOT NULL,
    submergence_ratio FLOAT NOT NULL,
    velocity        FLOAT DEFAULT 0.0,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          VARCHAR(50) DEFAULT 'lisflood',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Fast time-range queries (most recent predictions first)
CREATE INDEX IF NOT EXISTS idx_flood_pred_ts
    ON flood_prediction(timestamp DESC);

-- Spatial index for intersection queries
CREATE INDEX IF NOT EXISTS idx_flood_pred_geom
    ON flood_prediction USING GIST(geometry);


-- ────────────────────────────────────────────────────────────
-- road_risk: dynamic road segment weights
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS road_risk (
    id              SERIAL PRIMARY KEY,
    road_segment_id VARCHAR(100) NOT NULL,
    geometry        GEOMETRY(LineString, 4326),
    base_weight     FLOAT NOT NULL DEFAULT 1.0,
    dynamic_weight  FLOAT NOT NULL DEFAULT 1.0,
    max_submergence FLOAT DEFAULT 0.0,
    is_closed       BOOLEAN DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Spatial index for road–flood intersection
CREATE INDEX IF NOT EXISTS idx_road_risk_geom
    ON road_risk USING GIST(geometry);

-- Fast lookup by segment ID
CREATE INDEX IF NOT EXISTS idx_road_risk_segment
    ON road_risk(road_segment_id);
