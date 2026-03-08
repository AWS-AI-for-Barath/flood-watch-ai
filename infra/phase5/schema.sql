-- ============================================================
-- FloodWatch Phase 5 -- User Database Schema
-- Table: registered_users
-- ============================================================

-- Ensure PostGIS is enabled first
CREATE EXTENSION IF NOT EXISTS postgis;

-- Create the user registry table
CREATE TABLE IF NOT EXISTS registered_users (
    user_id             VARCHAR(100) PRIMARY KEY,
    phone_number        VARCHAR(20) NOT NULL,
    preferred_language  VARCHAR(10) DEFAULT 'en',
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    geom                GEOGRAPHY(POINT, 4326),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Essential spatial index for fast ST_Intersects queries
CREATE INDEX IF NOT EXISTS idx_users_geom
    ON registered_users USING GIST(geom);

-- Optional: Seed test users aligned with Phase 5 mock data
INSERT INTO registered_users (user_id, phone_number, preferred_language, latitude, longitude, geom)
VALUES
    ('U001', '+919876543210', 'en', 13.0827, 80.2707, ST_SetSRID(ST_MakePoint(80.2707, 13.0827), 4326)::geography),
    ('U002', '+919876543211', 'ta', 13.0600, 80.2400, ST_SetSRID(ST_MakePoint(80.2400, 13.0600), 4326)::geography),
    ('U003', '+919876543212', 'hi', 13.0450, 80.2350, ST_SetSRID(ST_MakePoint(80.2350, 13.0450), 4326)::geography)
ON CONFLICT (user_id) DO NOTHING;
