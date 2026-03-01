"""
routing_api.py — Core flood-aware routing endpoint logic.

Orchestrates the full routing workflow:
  1. Fetch latest flood predictions from PostGIS
  2. Update road weights via the road risk engine
  3. Query OSRM for a route
  4. Compute risk metrics along the route
  5. Return structured JSON response

Response schema:
    {
      "status": "ok" | "rerouted" | "blocked",
      "start": [lat, lon],
      "goal": [lat, lon],
      "route": [[lat, lon], ...],
      "risk_level": "low" | "moderate" | "high" | "severe",
      "max_submergence_ratio": float,
      "exposure_length": float,
      "predicted_arrival_risk": float
    }
"""

import logging
import math

from shapely.geometry import LineString, Point, shape

from phase4_routing.db.flood_store import get_latest_predictions
from phase4_routing.osrm.osrm_client import get_osrm_client
from phase4_routing.routing.risk_levels import get_risk_level

logger = logging.getLogger(__name__)


def _compute_route_risk(
    route_coords: list[list[float]],
    flood_features: list[dict],
) -> dict:
    """
    Compute risk metrics for a route against active flood polygons.

    Args:
        route_coords: List of [lat, lon] waypoints.
        flood_features: GeoJSON features from flood predictions.

    Returns:
        Dict with max_submergence_ratio, exposure_length (metres),
        and predicted_arrival_risk.
    """
    if not route_coords or not flood_features:
        return {
            "max_submergence_ratio": 0.0,
            "exposure_length": 0.0,
            "predicted_arrival_risk": 0.0,
        }

    # Build route line (convert lat,lon → lon,lat for Shapely)
    line_coords = [(c[1], c[0]) for c in route_coords]
    if len(line_coords) < 2:
        return {
            "max_submergence_ratio": 0.0,
            "exposure_length": 0.0,
            "predicted_arrival_risk": 0.0,
        }

    route_line = LineString(line_coords)
    total_length = route_line.length  # degrees (approx)

    max_submergence = 0.0
    exposure_length_deg = 0.0

    for feature in flood_features:
        try:
            polygon = shape(feature["geometry"])
        except Exception:
            continue

        if route_line.intersects(polygon):
            intersection = route_line.intersection(polygon)
            seg_length = intersection.length
            exposure_length_deg += seg_length

            sub_ratio = feature["properties"].get("submergence_ratio", 0.0)
            max_submergence = max(max_submergence, sub_ratio)

    # Convert degrees → metres (rough: 1 deg ≈ 111 km at equator)
    exposure_length_m = exposure_length_deg * 111_000

    # Predicted arrival risk: weighted combination
    exposure_fraction = (
        exposure_length_deg / total_length if total_length > 0 else 0.0
    )
    predicted_arrival_risk = min(
        1.0,
        0.6 * max_submergence + 0.4 * exposure_fraction,
    )

    return {
        "max_submergence_ratio": round(max_submergence, 4),
        "exposure_length": round(exposure_length_m, 2),
        "predicted_arrival_risk": round(predicted_arrival_risk, 4),
    }


def _determine_status(
    max_submergence: float,
    route_available: bool,
) -> str:
    """Determine route status based on risk."""
    if not route_available:
        return "blocked"
    if max_submergence > 0.7:
        return "blocked"
    if max_submergence > 0.2:
        return "rerouted"
    return "ok"


def handle_route_request(
    start: tuple[float, float],
    goal: tuple[float, float],
    use_mock_osrm: bool = False,
    prediction_window_minutes: int = 30,
) -> dict:
    """
    Handle a flood-aware routing request.

    Args:
        start: (latitude, longitude) of the origin.
        goal:  (latitude, longitude) of the destination.
        use_mock_osrm: If True, use the mock OSRM client.
        prediction_window_minutes: Time window for flood predictions.

    Returns:
        Structured route response dict.
    """
    logger.info("Route request: %s → %s", start, goal)

    # 1. Fetch latest flood predictions
    predictions = get_latest_predictions(minutes=prediction_window_minutes)
    flood_features = predictions.get("features", [])
    logger.info("Active flood polygons: %d", len(flood_features))

    # 2. Query OSRM for route
    osrm = get_osrm_client(mock=use_mock_osrm)
    osrm_result = osrm.get_route(start, goal)

    if osrm_result["status"] != "ok":
        logger.warning("OSRM returned error: %s", osrm_result.get("message"))
        return {
            "status": "blocked",
            "start": list(start),
            "goal": list(goal),
            "route": [],
            "risk_level": "severe",
            "max_submergence_ratio": 0.0,
            "exposure_length": 0.0,
            "predicted_arrival_risk": 1.0,
        }

    route_coords = osrm_result["route"]

    # 3. Compute risk metrics
    risk = _compute_route_risk(route_coords, flood_features)

    # 4. Determine status
    status = _determine_status(
        risk["max_submergence_ratio"],
        route_available=True,
    )

    risk_level = get_risk_level(risk["max_submergence_ratio"])

    response = {
        "status": status,
        "start": list(start),
        "goal": list(goal),
        "route": route_coords,
        "risk_level": risk_level,
        "max_submergence_ratio": risk["max_submergence_ratio"],
        "exposure_length": risk["exposure_length"],
        "predicted_arrival_risk": risk["predicted_arrival_risk"],
    }

    logger.info(
        "Route response: status=%s risk_level=%s max_sub=%.3f",
        status, risk_level, risk["max_submergence_ratio"],
    )

    return response
