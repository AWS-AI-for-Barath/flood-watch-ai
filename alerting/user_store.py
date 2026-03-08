"""
user_store.py -- PostGIS user registry for Phase 5 alerting.

Provides spatial queries against the registered_users table to find
users located inside predicted flood polygons.

Supports mock mode for local testing (FLOODWATCH_ALERT_MODE=mock).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# -- Mock Users (for local/test mode) ------------------------------------
_MOCK_USERS = [
    {
        "user_id": "U001",
        "phone_number": "+919876543210",
        "preferred_language": "en",
        "lat": 13.0827,
        "lon": 80.2707,
    },
    {
        "user_id": "U002",
        "phone_number": "+919876543211",
        "preferred_language": "ta",
        "lat": 13.0600,
        "lon": 80.2400,
    },
    {
        "user_id": "U003",
        "phone_number": "+919876543212",
        "preferred_language": "hi",
        "lat": 13.0450,
        "lon": 80.2350,
    },
]


def _get_db_connection():
    """Create a PostgreSQL connection using environment variables."""
    import psycopg2

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "floodwatch"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASS", ""),
    )


def get_affected_users(flood_polygons: dict) -> list:
    """
    Find registered users inside predicted flood zones.

    In production mode, executes a PostGIS ST_Intersects spatial
    join against the flood_prediction table.

    In mock mode, returns hardcoded test users that fall inside the
    provided GeoJSON polygons (using Shapely for in-memory check).

    Args:
        flood_polygons: GeoJSON FeatureCollection of flood predictions.

    Returns:
        List of user dicts with keys: user_id, phone_number,
        preferred_language, lat, lon, submergence_ratio,
        flood_zone_id.
    """
    mode = os.environ.get("FLOODWATCH_ALERT_MODE", "production")

    if mode == "mock":
        return _get_affected_users_mock(flood_polygons)

    return _get_affected_users_postgis()


def _get_affected_users_postgis() -> list:
    """
    Query PostGIS for users inside recent flood prediction polygons.

    Uses ST_Intersects spatial join between registered_users
    and flood_prediction tables.
    """
    conn = None
    try:
        conn = _get_db_connection()
        cur = conn.cursor()

        query = """
            SELECT DISTINCT
                u.user_id,
                u.phone_number,
                u.preferred_language,
                u.latitude,
                u.longitude,
                f.submergence_ratio,
                f.id AS flood_zone_id
            FROM registered_users u
            JOIN flood_prediction f
                ON ST_Intersects(u.geom, f.geometry)
            WHERE f.timestamp > NOW() - INTERVAL '5 minutes'
            ORDER BY f.submergence_ratio DESC;
        """

        cur.execute(query)
        rows = cur.fetchall()

        users = []
        for row in rows:
            users.append({
                "user_id": row[0],
                "phone_number": row[1],
                "preferred_language": row[2] or "en",
                "lat": float(row[3]) if row[3] else 0.0,
                "lon": float(row[4]) if row[4] else 0.0,
                "submergence_ratio": float(row[5]) if row[5] else 0.0,
                "flood_zone_id": f"zone_{row[6]}" if row[6] else "zone_0",
            })

        logger.info("PostGIS spatial query returned %d affected users", len(users))
        return users

    except Exception as e:
        logger.error("PostGIS user query failed: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def _get_affected_users_mock(flood_polygons: dict) -> list:
    """
    In-memory Shapely check for mock/testing mode.

    Preserves compatibility with the original Phase 5 test suite.
    """
    from shapely.geometry import Point, shape

    features = flood_polygons.get("features", [])
    if not features:
        return _MOCK_USERS

    affected = []
    for user in _MOCK_USERS:
        point = Point(user["lon"], user["lat"])
        for idx, feature in enumerate(features):
            try:
                polygon = shape(feature["geometry"])
                sub_ratio = feature.get("properties", {}).get(
                    "submergence_ratio", 0.0
                )
                if point.within(polygon) and sub_ratio >= 0.2:
                    affected.append({
                        **user,
                        "submergence_ratio": sub_ratio,
                        "flood_zone_id": feature.get("properties", {}).get(
                            "zone_id", f"zone_{idx}"
                        ),
                    })
                    break
            except Exception:
                continue

    logger.info("Mock spatial check returned %d affected users", len(affected))
    return affected


def register_user(
    user_id: str,
    phone_number: str,
    latitude: float,
    longitude: float,
    preferred_language: str = "en",
) -> bool:
    """
    Register a new user in the PostGIS database.

    Args:
        user_id: Unique identifier (e.g., device UUID).
        phone_number: E.164 format phone number.
        latitude: User's latitude.
        longitude: User's longitude.
        preferred_language: ISO 639-1 language code.

    Returns:
        True on success, False on failure.
    """
    mode = os.environ.get("FLOODWATCH_ALERT_MODE", "production")
    if mode == "mock":
        logger.info("Mock register_user: %s at (%s, %s)", user_id, latitude, longitude)
        return True

    conn = None
    try:
        conn = _get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO registered_users
                (user_id, phone_number, preferred_language, latitude, longitude, geom)
            VALUES
                (%s, %s, %s, %s, %s,
                 ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)
            ON CONFLICT (user_id) DO UPDATE SET
                phone_number = EXCLUDED.phone_number,
                preferred_language = EXCLUDED.preferred_language,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                geom = EXCLUDED.geom;
            """,
            (user_id, phone_number, preferred_language,
             latitude, longitude, longitude, latitude),
        )
        conn.commit()
        logger.info("Registered user %s", user_id)
        return True

    except Exception as e:
        logger.error("Failed to register user %s: %s", user_id, e)
        return False
    finally:
        if conn:
            conn.close()


def get_all_users() -> list:
    """
    Return all registered users.

    Returns:
        List of user dicts.
    """
    mode = os.environ.get("FLOODWATCH_ALERT_MODE", "production")
    if mode == "mock":
        return _MOCK_USERS

    conn = None
    try:
        conn = _get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, phone_number, preferred_language, "
            "latitude, longitude FROM registered_users"
        )
        rows = cur.fetchall()
        return [
            {
                "user_id": r[0],
                "phone_number": r[1],
                "preferred_language": r[2] or "en",
                "lat": float(r[3]) if r[3] else 0.0,
                "lon": float(r[4]) if r[4] else 0.0,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Failed to fetch users: %s", e)
        return []
    finally:
        if conn:
            conn.close()
