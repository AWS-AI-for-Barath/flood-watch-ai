"""
flood_store.py — CRUD operations for flood predictions and road risks.

Provides a unified API that works against both the MockConnection
(local testing) and a real PostGIS database (production).
"""

import json
import logging
from datetime import datetime, timezone, timedelta

from phase4_routing.db.connection import get_connection, get_db_mode

logger = logging.getLogger(__name__)


# ── Flood Predictions ───────────────────────────────────────────────

def store_predictions(geojson: dict) -> int:
    """
    Insert flood polygons from a GeoJSON FeatureCollection.

    Args:
        geojson: FeatureCollection with flood features. Each feature
                 must have ``submergence_ratio`` and ``timestamp`` in
                 its properties.

    Returns:
        Number of features inserted.
    """
    features = geojson.get("features", [])
    if not features:
        logger.warning("store_predictions called with empty FeatureCollection")
        return 0

    conn = get_connection()
    mode = get_db_mode()

    if mode == "mock":
        for feature in features:
            conn.flood_predictions.append({
                "geometry": feature["geometry"],
                "submergence_ratio": feature["properties"]["submergence_ratio"],
                "velocity": feature["properties"].get("velocity", 0.0),
                "timestamp": feature["properties"].get(
                    "timestamp",
                    datetime.now(timezone.utc).isoformat(),
                ),
                "source": "lisflood",
            })
        logger.info("Mock DB: stored %d flood predictions", len(features))
    else:
        cursor = conn.cursor()
        for feature in features:
            props = feature["properties"]
            geom_json = json.dumps(feature["geometry"])
            cursor.execute(
                """
                INSERT INTO flood_prediction
                    (geometry, submergence_ratio, velocity, timestamp, source)
                VALUES
                    (ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                     %s, %s, %s, %s)
                """,
                (
                    geom_json,
                    props["submergence_ratio"],
                    props.get("velocity", 0.0),
                    props.get("timestamp", datetime.now(timezone.utc)),
                    "lisflood",
                ),
            )
        conn.commit()
        cursor.close()
        logger.info("PostGIS: stored %d flood predictions", len(features))

    return len(features)


def get_latest_predictions(minutes: int = 30) -> dict:
    """
    Fetch recent flood predictions as a GeoJSON FeatureCollection.

    Args:
        minutes: Time window — predictions newer than this many
                 minutes ago are returned.

    Returns:
        GeoJSON FeatureCollection of active flood polygons.
    """
    conn = get_connection()
    mode = get_db_mode()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    features = []

    if mode == "mock":
        for pred in conn.flood_predictions:
            ts = pred["timestamp"]
            if isinstance(ts, str):
                # Parse ISO timestamp, handle 'Z' suffix
                ts_clean = ts.replace("Z", "+00:00")
                try:
                    ts = datetime.fromisoformat(ts_clean)
                except ValueError:
                    ts = datetime.now(timezone.utc)

            if ts >= cutoff:
                features.append({
                    "type": "Feature",
                    "geometry": pred["geometry"],
                    "properties": {
                        "submergence_ratio": pred["submergence_ratio"],
                        "velocity": pred.get("velocity", 0.0),
                        "timestamp": pred["timestamp"],
                    },
                })
    else:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ST_AsGeoJSON(geometry)::json,
                   submergence_ratio, velocity, timestamp
            FROM flood_prediction
            WHERE timestamp >= %s
            ORDER BY timestamp DESC
            """,
            (cutoff,),
        )
        for row in cursor.fetchall():
            features.append({
                "type": "Feature",
                "geometry": row[0],
                "properties": {
                    "submergence_ratio": row[1],
                    "velocity": row[2],
                    "timestamp": row[3].isoformat(),
                },
            })
        cursor.close()

    logger.info("Retrieved %d active flood predictions (last %d min)",
                len(features), minutes)

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def clear_old_predictions(hours: int = 24) -> int:
    """
    Delete flood predictions older than ``hours``.

    Args:
        hours: Age threshold.

    Returns:
        Number of records deleted.
    """
    conn = get_connection()
    mode = get_db_mode()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    if mode == "mock":
        before = len(conn.flood_predictions)
        conn.flood_predictions = [
            p for p in conn.flood_predictions
            if _parse_ts(p["timestamp"]) >= cutoff
        ]
        deleted = before - len(conn.flood_predictions)
    else:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM flood_prediction WHERE timestamp < %s", (cutoff,)
        )
        deleted = cursor.rowcount
        conn.commit()
        cursor.close()

    logger.info("Cleared %d old predictions (older than %dh)", deleted, hours)
    return deleted


# ── Road Risks ──────────────────────────────────────────────────────

def upsert_road_risk(
    road_segment_id: str,
    base_weight: float,
    dynamic_weight: float,
    max_submergence: float,
    is_closed: bool,
    geometry: dict | None = None,
) -> None:
    """
    Insert or update a road segment's risk data.

    Args:
        road_segment_id: Unique segment identifier.
        base_weight:     Original weight.
        dynamic_weight:  Flood-adjusted weight.
        max_submergence: Highest submergence ratio on this segment.
        is_closed:       True if segment is impassable.
        geometry:        Optional GeoJSON LineString geometry.
    """
    conn = get_connection()
    mode = get_db_mode()

    if mode == "mock":
        # Update existing or append new
        for risk in conn.road_risks:
            if risk["road_segment_id"] == road_segment_id:
                risk.update({
                    "base_weight": base_weight,
                    "dynamic_weight": dynamic_weight,
                    "max_submergence": max_submergence,
                    "is_closed": is_closed,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                if geometry:
                    risk["geometry"] = geometry
                return

        conn.road_risks.append({
            "road_segment_id": road_segment_id,
            "geometry": geometry,
            "base_weight": base_weight,
            "dynamic_weight": dynamic_weight,
            "max_submergence": max_submergence,
            "is_closed": is_closed,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        cursor = conn.cursor()
        geom_sql = "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)" if geometry else "NULL"
        cursor.execute(
            f"""
            INSERT INTO road_risk
                (road_segment_id, geometry, base_weight, dynamic_weight,
                 max_submergence, is_closed, updated_at)
            VALUES (%s, {geom_sql}, %s, %s, %s, %s, NOW())
            ON CONFLICT (road_segment_id) DO UPDATE SET
                base_weight = EXCLUDED.base_weight,
                dynamic_weight = EXCLUDED.dynamic_weight,
                max_submergence = EXCLUDED.max_submergence,
                is_closed = EXCLUDED.is_closed,
                updated_at = NOW()
            """,
            (
                road_segment_id,
                *([json.dumps(geometry)] if geometry else []),
                base_weight,
                dynamic_weight,
                max_submergence,
                is_closed,
            ),
        )
        conn.commit()
        cursor.close()


def get_road_risks() -> list:
    """
    Fetch all road risk entries.

    Returns:
        List of road risk dicts.
    """
    conn = get_connection()
    mode = get_db_mode()

    if mode == "mock":
        return list(conn.road_risks)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT road_segment_id, ST_AsGeoJSON(geometry)::json,
               base_weight, dynamic_weight, max_submergence, is_closed
        FROM road_risk
        ORDER BY updated_at DESC
        """
    )
    results = []
    for row in cursor.fetchall():
        results.append({
            "road_segment_id": row[0],
            "geometry": row[1],
            "base_weight": row[2],
            "dynamic_weight": row[3],
            "max_submergence": row[4],
            "is_closed": row[5],
        })
    cursor.close()
    return results


# ── Helpers ─────────────────────────────────────────────────────────

def _parse_ts(ts) -> datetime:
    """Parse a timestamp string or return it if already a datetime."""
    if isinstance(ts, datetime):
        return ts
    ts_clean = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts_clean)
    except ValueError:
        return datetime.now(timezone.utc)
