"""
transformFloodPolygon — Phase 3 Lambda Handler

Triggered by S3 ObjectCreated on analysis/* prefix.
Reads AI analysis + metadata, generates PostGIS-backed flood polygon,
stores in RDS, and returns GeoJSON matching Phase 5 contract.

Runtime: Python 3.10 | Memory: 512MB | Timeout: 30s
"""

import json
import logging
import os
import uuid as uuid_lib

import boto3
import psycopg2

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

BUCKET = os.environ.get("BUCKET_NAME", "floodwatch-uploads")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "floodwatch")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS")

# Reference height in meters (assumed average obstacle height)
REFERENCE_HEIGHT_M = 1.5

# Radius mapping: submergence_ratio → buffer radius in meters
# Radius mapping: submergence_ratio → buffer radius in meters
RADIUS_MAP = [
    (0.7, 600),
    (0.4, 300),
    (0.2, 120),
    (0.0, 50),
]


def get_db_connection():
    """Create a PostgreSQL connection with PostGIS."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=5,
    )


# ================================================================
#  CORE FUNCTIONS
# ================================================================

def fetchAIResult(bucket, key):
    """
    Read analysis/<uuid>.json from S3.
    Returns dict with: people_trapped, infrastructure_damage, severity, submergence_ratio
    """
    logger.info(f"[fetchAIResult] Reading s3://{bucket}/{key}")
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    result = json.loads(body)
    logger.info(f"[fetchAIResult] AI result: {result}")
    return result


def fetchMetadata(bucket, uuid_str):
    """
    Read metadata/<uuid>.json from S3.
    Returns dict with: lat, lon, timestamp, device info, etc.
    """
    key = f"metadata/{uuid_str}.json"
    logger.info(f"[fetchMetadata] Reading s3://{bucket}/{key}")
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        metadata = json.loads(body)
        logger.info(f"[fetchMetadata] Metadata: lat={metadata.get('lat')}, lon={metadata.get('lon')}")
        return metadata
    except s3.exceptions.NoSuchKey:
        logger.warning(f"[fetchMetadata] No metadata found for {uuid_str}, using defaults")
        return None


def getBaseElevation(conn, lat, lon):
    """
    Query nearest baseline DEM elevation from PostGIS.
    Falls back to 0 if no DEM data available.
    """
    logger.info(f"[getBaseElevation] Querying DEM for ({lat}, {lon})")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT elevation
                FROM dem_table
                ORDER BY geom <-> ST_SetSRID(ST_Point(%s, %s), 4326)
                LIMIT 1;
            """, (lon, lat))
            row = cur.fetchone()
            if row:
                elevation = float(row[0])
                logger.info(f"[getBaseElevation] Nearest elevation: {elevation}m")
                return elevation
    except psycopg2.Error as e:
        logger.warning(f"[getBaseElevation] DEM query failed: {e}")

    # Fallback: assume sea level
    logger.info("[getBaseElevation] No DEM data, using default elevation 0m")
    return 0.0


def computeWaterSurface(base_elevation, submergence_ratio):
    """
    Compute water surface elevation.
    Formula: water_surface = base_elevation + (submergence_ratio × 1.5m)
    """
    water_surface = base_elevation + (submergence_ratio * REFERENCE_HEIGHT_M)
    logger.info(
        f"[computeWaterSurface] base={base_elevation}m + "
        f"({submergence_ratio} × {REFERENCE_HEIGHT_M}m) = {water_surface}m"
    )
    return round(water_surface, 2)


def _get_buffer_radius(submergence_ratio):
    """Map submergence_ratio to buffer radius in meters."""
    for threshold, radius in RADIUS_MAP:
        if submergence_ratio >= threshold:
            return radius
    return 20  # minimum fallback


def generateFloodPolygon(conn, lat, lon, submergence_ratio):
    """
    Generate a flood polygon using PostGIS ST_Buffer.
    Returns GeoJSON geometry dict.
    """
    radius = _get_buffer_radius(submergence_ratio)
    logger.info(
        f"[generateFloodPolygon] ratio={submergence_ratio} → "
        f"radius={radius}m at ({lat}, {lon})"
    )

    with conn.cursor() as cur:
        cur.execute("""
            SELECT ST_AsGeoJSON(
                ST_Buffer(
                    ST_SetSRID(ST_Point(%s, %s), 4326)::geography,
                    %s
                )::geometry
            );
        """, (lon, lat, radius))
        row = cur.fetchone()

    if not row or not row[0]:
        raise RuntimeError("PostGIS ST_Buffer returned no result")

    geojson_geom = json.loads(row[0])
    logger.info(f"[generateFloodPolygon] Generated polygon with {len(geojson_geom.get('coordinates', [[]])[-1])} vertices")
    return geojson_geom


def storeFloodPolygon(conn, polygon_id, geojson_geom, submergence_ratio,
                      severity, timestamp, water_surface_elevation):
    """
    INSERT the flood polygon into the flood_layer table.
    """
    logger.info(f"[storeFloodPolygon] Storing polygon {polygon_id}")

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO flood_layer (id, geom, submergence_ratio, severity,
                                     timestamp, water_surface_elevation)
            VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                    %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                geom = EXCLUDED.geom,
                submergence_ratio = EXCLUDED.submergence_ratio,
                severity = EXCLUDED.severity,
                timestamp = EXCLUDED.timestamp,
                water_surface_elevation = EXCLUDED.water_surface_elevation;
        """, (
            polygon_id,
            json.dumps(geojson_geom),
            submergence_ratio,
            severity,
            timestamp,
            water_surface_elevation,
        ))
    conn.commit()
    logger.info(f"[storeFloodPolygon] Stored successfully")


def formatGeoJSON(polygon_id, geojson_geom, submergence_ratio, severity, timestamp):
    """
    Format output as GeoJSON FeatureCollection matching Phase 5 contract.

    Contract:
    {
      "type": "FeatureCollection",
      "features": [{
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [...] },
        "properties": {
          "zone_id": "zone_<id>",
          "submergence_ratio": float,
          "severity": string,
          "timestamp": ISO8601 string
        }
      }]
    }
    """
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": geojson_geom,
                "properties": {
                    "zone_id": f"zone_{polygon_id}",
                    "submergence_ratio": submergence_ratio,
                    "severity": severity,
                    "timestamp": timestamp,
                },
            }
        ],
    }
    return feature_collection


# ================================================================
#  LAMBDA HANDLER
# ================================================================

def handler(event, context):
    """
    S3 trigger handler for analysis/* objects.
    Full pipeline: AI result → metadata → DEM → water surface → polygon → store → GeoJSON
    """
    logger.info(f"[transformFloodPolygon] Event: {json.dumps(event)[:500]}")

    try:
        # Parse S3 event
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"].replace("+", " ")
        key = __import__("urllib.parse", fromlist=["unquote"]).unquote(key)

        logger.info(f"[transformFloodPolygon] Processing s3://{bucket}/{key}")

        # Extract UUID from key: analysis/<uuid>.json → <uuid>
        filename = key.split("/")[-1]
        uuid_str = filename.replace(".json", "")

        # Step 1: Fetch AI result
        ai_result = fetchAIResult(bucket, key)
        submergence_ratio = float(ai_result.get("submergence_ratio", 0.0))
        severity = ai_result.get("severity", "unknown")

        # Step 2: Fetch metadata (lat, lon, timestamp)
        metadata = fetchMetadata(bucket, uuid_str)
        if metadata:
            lat = float(metadata.get("lat", metadata.get("latitude", 13.08)))
            lon = float(metadata.get("lon", metadata.get("longitude", 80.27)))
            timestamp = metadata.get("timestamp", metadata.get("captured_at", "2026-01-01T00:00:00Z"))
        else:
            # Fallback defaults (Chennai)
            lat, lon = 13.08, 80.27
            timestamp = "2026-01-01T00:00:00Z"
            logger.warning("[transformFloodPolygon] Using fallback coordinates")

        # Step 3–7: PostGIS operations
        conn = get_db_connection()
        try:
            # Step 3: Get baseline elevation
            base_elevation = getBaseElevation(conn, lat, lon)

            # Step 4: Compute water surface
            water_surface = computeWaterSurface(base_elevation, submergence_ratio)

            # Step 5: Generate flood polygon
            geojson_geom = generateFloodPolygon(conn, lat, lon, submergence_ratio)

            # Step 6: Store in PostGIS
            polygon_id = uuid_str
            storeFloodPolygon(
                conn, polygon_id, geojson_geom,
                submergence_ratio, severity, timestamp, water_surface
            )

            # Step 7: Format GeoJSON
            geojson_output = formatGeoJSON(
                polygon_id, geojson_geom,
                submergence_ratio, severity, timestamp
            )
        finally:
            conn.close()

        logger.info(f"[transformFloodPolygon] Complete: {json.dumps(geojson_output)[:300]}")

        return {
            "statusCode": 200,
            "body": json.dumps(geojson_output),
        }

    except Exception as e:
        logger.error(f"[transformFloodPolygon] FATAL: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
