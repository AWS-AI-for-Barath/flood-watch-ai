"""
alert_generator.py — Main alert generation logic for FloodWatch Phase 5.

Combines geo_utils (point-in-polygon) and severity mapping to produce
structured JSON alerts for every affected user.
"""

from typing import List

from .geo_utils import is_user_affected, load_flood_polygons
from .severity import get_severity

# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------
_MESSAGES = {
    "low": (
        "Flood advisory: Minor water-level rise detected near your location. "
        "Stay informed and monitor local updates."
    ),
    "moderate": (
        "Flood warning: Moderate water levels detected near your location. "
        "Avoid low-lying areas and stay alert."
    ),
    "high": (
        "Flood warning: High water levels detected near your location. "
        "Avoid travel and move to higher ground."
    ),
    "severe": (
        "Flood emergency: Severe flooding detected near your location. "
        "Evacuate immediately to the nearest relief center."
    ),
}


def _build_message(severity: str) -> str:
    """Return a user-facing alert message with optional evacuation notice."""
    base = _MESSAGES.get(severity, _MESSAGES["low"])
    if severity in ("high", "severe"):
        base += " Evacuation is strongly recommended."
    return base


def generate_alerts(
    flood_geojson: dict,
    users: list,
    threshold: float = 0.35,
) -> List[dict]:
    """
    Generate flood alerts for users located inside predicted flood zones.

    Args:
        flood_geojson: GeoJSON FeatureCollection with flood polygons
                       (each feature must have ``submergence_ratio``
                       and optionally ``zone_id`` in properties).
        users: List of user dicts, each with ``user_id``, ``phone``,
               ``lat``, and ``lon``.
        threshold: Minimum submergence_ratio to trigger an alert.

    Returns:
        List of alert dicts matching the FloodWatch alert schema::

            {
                "user_id": "U123",
                "phone": "+91XXXXXXXXXX",
                "lat": 13.08,
                "lon": 80.27,
                "severity": "high",
                "submergence_ratio": 0.62,
                "flood_zone_id": "zone_2",
                "message": "..."
            }
    """
    polygons = load_flood_polygons(flood_geojson)
    alerts: List[dict] = []

    for user in users:
        for polygon in polygons:
            if is_user_affected(user, polygon, threshold):
                severity = get_severity(polygon["submergence_ratio"])
                alerts.append(
                    {
                        "user_id": user["user_id"],
                        "phone": user["phone"],
                        "lat": user["lat"],
                        "lon": user["lon"],
                        "severity": severity,
                        "submergence_ratio": round(
                            polygon["submergence_ratio"], 4
                        ),
                        "flood_zone_id": polygon["zone_id"],
                        "message": _build_message(severity),
                    }
                )

    return alerts
