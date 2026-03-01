"""
road_risk_updater.py — Dynamic road risk update engine.

Fetches the latest flood prediction polygons, intersects them with
road segments, computes dynamic weights using the tiered multipliers
in ``risk_levels.py``, and persists results to the ``road_risk`` table.
"""

import logging
from datetime import datetime, timezone

from shapely.geometry import LineString, shape

from phase4_routing.db.flood_store import (
    get_latest_predictions,
    get_road_risks,
    upsert_road_risk,
)
from phase4_routing.routing.risk_levels import (
    compute_weight,
    get_risk_level,
    is_road_closed,
)

logger = logging.getLogger(__name__)


def _geojson_to_shapely(geojson_geom: dict):
    """Convert a GeoJSON geometry dict to a Shapely object."""
    return shape(geojson_geom)


def intersect_road_with_floods(
    road_geometry,
    flood_polygons: list,
) -> float:
    """
    Find the maximum submergence ratio among all flood polygons that
    intersect a road segment.

    Args:
        road_geometry: Shapely LineString of the road segment.
        flood_polygons: List of dicts with 'geometry' (Shapely) and
                        'submergence_ratio' keys.

    Returns:
        Maximum submergence ratio affecting this road (0.0 if none).
    """
    max_submergence = 0.0

    for polygon in flood_polygons:
        if road_geometry.intersects(polygon["geometry"]):
            max_submergence = max(
                max_submergence,
                polygon["submergence_ratio"],
            )

    return max_submergence


def update_road_risks(
    road_segments: list | None = None,
    prediction_window_minutes: int = 30,
) -> dict:
    """
    Update dynamic weights for all road segments.

    Workflow:
      1. Fetch latest flood predictions from DB
      2. For each road segment, intersect with flood polygons
      3. Compute dynamic weight based on max submergence
      4. Persist updated risk to road_risk table

    Args:
        road_segments: Optional list of road segment dicts, each with
                       'road_segment_id', 'geometry' (GeoJSON), and
                       'base_weight'. If None, reads existing segments
                       from DB.
        prediction_window_minutes: How recent the predictions should be.

    Returns:
        Summary dict with counts and details.
    """
    # Fetch latest flood predictions
    predictions = get_latest_predictions(minutes=prediction_window_minutes)
    flood_features = predictions.get("features", [])

    if not flood_features:
        logger.info("No active flood predictions — all roads at baseline risk")
        return {
            "updated": 0,
            "closed": 0,
            "total_segments": 0,
            "flood_polygons": 0,
        }

    # Convert flood geometries to Shapely
    flood_polygons = []
    for feature in flood_features:
        flood_polygons.append({
            "geometry": _geojson_to_shapely(feature["geometry"]),
            "submergence_ratio": feature["properties"]["submergence_ratio"],
        })

    # Get road segments (from arg or DB)
    if road_segments is None:
        road_segments = get_road_risks()

    updated_count = 0
    closed_count = 0

    for segment in road_segments:
        seg_id = segment["road_segment_id"]
        base_weight = segment.get("base_weight", 1.0)
        geom_data = segment.get("geometry")

        if geom_data is None:
            continue

        # Convert geometry
        if isinstance(geom_data, dict):
            road_geom = _geojson_to_shapely(geom_data)
        else:
            road_geom = geom_data

        # Compute max submergence from all overlapping flood polygons
        max_sub = intersect_road_with_floods(road_geom, flood_polygons)

        # Compute dynamic weight
        dynamic_weight = compute_weight(base_weight, max_sub)
        closed = is_road_closed(max_sub)

        # Persist
        upsert_road_risk(
            road_segment_id=seg_id,
            base_weight=base_weight,
            dynamic_weight=dynamic_weight,
            max_submergence=max_sub,
            is_closed=closed,
            geometry=geom_data if isinstance(geom_data, dict) else None,
        )

        updated_count += 1
        if closed:
            closed_count += 1

        logger.debug(
            "Segment %s: submergence=%.3f weight=%.1f closed=%s",
            seg_id, max_sub, dynamic_weight, closed,
        )

    summary = {
        "updated": updated_count,
        "closed": closed_count,
        "total_segments": len(road_segments),
        "flood_polygons": len(flood_polygons),
    }

    logger.info(
        "Road risk update complete: %d/%d segments updated, %d closed",
        updated_count, len(road_segments), closed_count,
    )

    return summary
