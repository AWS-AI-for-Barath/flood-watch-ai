"""
geo_utils.py — Point-in-polygon utilities for flood alerting.

Loads flood polygons from GeoJSON and checks whether a user's location
falls inside a predicted flood zone above a submergence threshold.
"""

from typing import Dict, List

from shapely.geometry import Point, shape


def load_flood_polygons(flood_geojson: dict) -> List[Dict]:
    """
    Extract flood polygons from a GeoJSON FeatureCollection.

    Each returned dict contains:
        - ``geometry``: Shapely polygon object
        - ``submergence_ratio``: float (0–1)
        - ``zone_id``: identifier string from feature properties

    Args:
        flood_geojson: A GeoJSON FeatureCollection with flood features.

    Returns:
        List of polygon dicts ready for spatial queries.
    """
    polygons = []

    for idx, feature in enumerate(flood_geojson.get("features", [])):
        props = feature.get("properties", {})
        geometry = shape(feature["geometry"])
        zone_id = props.get("zone_id", f"zone_{idx}")

        polygons.append(
            {
                "geometry": geometry,
                "submergence_ratio": float(props.get("submergence_ratio", 0.0)),
                "zone_id": zone_id,
            }
        )

    return polygons


def is_user_affected(
    user: dict, polygon: dict, threshold: float = 0.35
) -> bool:
    """
    Check if a user is inside a flood polygon and the submergence ratio
    exceeds *threshold*.

    Args:
        user: Dict with ``lat`` and ``lon`` keys.
        polygon: Polygon dict returned by :func:`load_flood_polygons`.
        threshold: Minimum submergence_ratio to consider the user affected.

    Returns:
        True if the user's location is within the polygon **and** the
        polygon's submergence_ratio ≥ threshold.
    """
    point = Point(user["lon"], user["lat"])
    return (
        point.within(polygon["geometry"])
        and polygon["submergence_ratio"] >= threshold
    )
