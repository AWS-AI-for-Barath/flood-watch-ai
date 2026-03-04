-- ============================================================
-- FloodWatch Phase 3 — PostGIS Schema
-- Run this in your RDS PostgreSQL instance
-- ============================================================

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- Flood polygon storage
-- ============================================================

CREATE TABLE IF NOT EXISTS flood_layer (
    id              UUID PRIMARY KEY,
    geom            GEOMETRY(POLYGON, 4326),
    submergence_ratio FLOAT,
    severity        TEXT,
    timestamp       TIMESTAMPTZ,
    water_surface_elevation FLOAT
);

-- Spatial index for fast geofencing queries (Phase 5)
CREATE INDEX IF NOT EXISTS flood_geom_idx
ON flood_layer USING GIST (geom);

-- ============================================================
-- DEM (Digital Elevation Model) baseline table
-- Stores nearest-neighbor elevation points for water surface
-- computation. Seed with a few points for your target area.
-- ============================================================

CREATE TABLE IF NOT EXISTS dem_table (
    id      SERIAL PRIMARY KEY,
    geom    GEOMETRY(POINT, 4326),
    elevation FLOAT  -- meters above sea level
);

CREATE INDEX IF NOT EXISTS dem_geom_idx
ON dem_table USING GIST (geom);

-- ============================================================
-- Seed DEM data (Chennai metro area — approximate elevations)
-- In production, import a real DEM raster using raster2pgsql.
-- ============================================================

INSERT INTO dem_table (geom, elevation) VALUES
    (ST_SetSRID(ST_Point(80.27, 13.08), 4326), 6.5),   -- Chennai central
    (ST_SetSRID(ST_Point(80.22, 13.02), 4326), 8.2),   -- Adyar area
    (ST_SetSRID(ST_Point(80.25, 13.05), 4326), 5.1),   -- T. Nagar
    (ST_SetSRID(ST_Point(80.30, 13.10), 4326), 4.8),   -- Perambur
    (ST_SetSRID(ST_Point(80.35, 13.15), 4326), 7.3),   -- Kolathur
    (ST_SetSRID(ST_Point(80.20, 13.00), 4326), 3.2),   -- Guindy
    (ST_SetSRID(ST_Point(80.28, 13.12), 4326), 5.9),   -- Kilpauk
    (ST_SetSRID(ST_Point(80.32, 13.07), 4326), 4.1),   -- Royapuram
    (ST_SetSRID(ST_Point(80.24, 13.09), 4326), 6.0),   -- Nungambakkam
    (ST_SetSRID(ST_Point(80.26, 13.04), 4326), 5.5);   -- Saidapet

-- Verify the setup
SELECT 'flood_layer table' AS item, COUNT(*) AS rows FROM flood_layer
UNION ALL
SELECT 'dem_table table', COUNT(*) FROM dem_table;
