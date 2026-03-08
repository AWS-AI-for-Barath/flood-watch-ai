"""
alert_generator.py — Main alert generation logic for FloodWatch Phase 5.

Combines spatial user detection (PostGIS), severity mapping,
multilingual message templates, and dispatch orchestration
to produce structured JSON alerts for every affected user.

Preserves the original ``generate_alerts()`` function signature
and return schema for backward compatibility.
"""

import logging
from typing import List

from .message_templates import get_alert_message
from .severity import SEVERITY_RANK, get_severity
from .user_store import get_affected_users

logger = logging.getLogger(__name__)


def generate_alerts(
    flood_geojson: dict,
    users: list = None,
    threshold: float = 0.2,
) -> List[dict]:
    """
    Generate flood alerts for users located inside predicted flood zones.

    In production mode, ``users`` param is ignored — users are detected
    via PostGIS ``ST_Intersects`` spatial queries. In mock mode, the
    ``users`` param is used if provided (backward-compatible with tests).

    Args:
        flood_geojson: GeoJSON FeatureCollection with flood polygons.
                       Each feature must have ``submergence_ratio``
                       and optionally ``zone_id`` in properties.
        users: (Optional) List of user dicts for mock/test mode.
               Ignored in production mode.
        threshold: Minimum submergence_ratio to trigger an alert.

    Returns:
        List of alert dicts matching the FloodWatch alert schema::

            {
                "user_id": "U123",
                "phone": "+91XXXXXXXXXX",
                "phone_number": "+91XXXXXXXXXX",
                "lat": 13.08,
                "lon": 80.27,
                "severity": "danger",
                "submergence_ratio": 0.62,
                "flood_zone_id": "zone_2",
                "message": "...",
                "preferred_language": "en"
            }
    """
    # When users are explicitly provided (test/legacy mode), use Shapely path
    if users is not None:
        affected_users = _legacy_user_check(flood_geojson, users, threshold)
    else:
        # Production mode: PostGIS spatial query (or mock fallback)
        affected_users = get_affected_users(flood_geojson)

    alerts: List[dict] = []

    for user in affected_users:
        sub_ratio = user.get("submergence_ratio", 0.0)

        # Skip below threshold
        if sub_ratio < threshold:
            continue

        severity = get_severity(sub_ratio)
        language = user.get("preferred_language", "en")
        message = get_alert_message(severity, language)

        phone = user.get("phone_number", user.get("phone", ""))

        alerts.append({
            "user_id": user["user_id"],
            "phone": phone,
            "phone_number": phone,
            "lat": user.get("lat", 0.0),
            "lon": user.get("lon", 0.0),
            "severity": severity,
            "submergence_ratio": round(sub_ratio, 4),
            "flood_zone_id": user.get("flood_zone_id", "zone_0"),
            "message": message,
            "preferred_language": language,
        })

    logger.info("Generated %d alerts from %d affected users", len(alerts), len(affected_users))
    return alerts


def _legacy_user_check(
    flood_geojson: dict, users: list, threshold: float
) -> list:
    """
    Legacy in-memory Shapely check for backward compatibility with
    the original test_alerts.py.

    Uses ``geo_utils.is_user_affected`` and ``geo_utils.load_flood_polygons``
    to preserve the original Phase 5 mock behaviour.
    """
    from .geo_utils import is_user_affected, load_flood_polygons

    polygons = load_flood_polygons(flood_geojson)
    affected = []

    for user in users:
        for polygon in polygons:
            if is_user_affected(user, polygon, threshold):
                affected.append({
                    "user_id": user["user_id"],
                    "phone_number": user.get("phone", user.get("phone_number", "")),
                    "preferred_language": user.get("preferred_language", "en"),
                    "lat": user.get("lat", 0.0),
                    "lon": user.get("lon", 0.0),
                    "submergence_ratio": polygon["submergence_ratio"],
                    "flood_zone_id": polygon["zone_id"],
                })
                break  # Only alert once per user

    return affected
