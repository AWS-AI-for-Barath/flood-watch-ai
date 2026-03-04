"""
flood_propagation.py — DEM-aware hydrodynamic flood propagation.

Uses real terrain elevation data from PostGIS `dem_table` to predict
short-term flood spread from Phase 3 flood polygons.

Process:
  1. Fetch current flood polygons from Phase 3 `flood_layer`
  2. Query DEM elevation grid around each flood polygon
  3. Compute terrain slope and flow direction
  4. Expand flood zones downstream (cells below water surface elevation)
  5. Return predicted flood polygons as GeoJSON FeatureCollection

This replaces the mock random-raster approach with real terrain-aware
flood propagation.
"""

import json
import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Propagation parameters
PROPAGATION_RADIUS_DEG = 0.02    # ~2.2 km search radius around each flood
GRID_RESOLUTION_DEG = 0.001      # ~111 m cell size
DEPTH_DECAY_FACTOR = 0.85        # water depth reduction per propagation step
MIN_DEPTH_THRESHOLD = 0.05       # stop propagating below this depth (metres)
MAX_PROPAGATION_STEPS = 5        # maximum iterations of expansion


def _query_dem_grid(conn, center_lat: float, center_lon: float,
                    radius_deg: float = PROPAGATION_RADIUS_DEG) -> list:
    """
    Query DEM elevation points from PostGIS within a bounding box.

    Args:
        conn: psycopg2 connection.
        center_lat: Centre latitude.
        center_lon: Centre longitude.
        radius_deg: Search radius in degrees.

    Returns:
        List of (lat, lon, elevation_m) tuples.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ST_Y(geom) AS lat,
               ST_X(geom) AS lon,
               elevation_m
        FROM dem_table
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        ORDER BY elevation_m ASC
        """,
        (
            center_lon - radius_deg,     # xmin
            center_lat - radius_deg,     # ymin
            center_lon + radius_deg,     # xmax
            center_lat + radius_deg,     # ymax
        ),
    )
    rows = cursor.fetchall()
    cursor.close()
    return [(r[0], r[1], r[2]) for r in rows]


def _compute_flow_targets(dem_points: list, water_surface_elev: float,
                          source_lat: float, source_lon: float) -> list:
    """
    Identify DEM cells that would be flooded by water at a given elevation.

    Water flows to cells whose terrain elevation is below the water surface.
    Cells are sorted by elevation (lowest first = most likely to flood).

    Args:
        dem_points: List of (lat, lon, elevation_m) tuples.
        water_surface_elev: Current water surface elevation in metres.
        source_lat: Flood source latitude.
        source_lon: Flood source longitude.

    Returns:
        List of dicts with lat, lon, depth, distance for flooded cells.
    """
    targets = []
    for lat, lon, elev in dem_points:
        depth = water_surface_elev - elev
        if depth > MIN_DEPTH_THRESHOLD:
            # Distance from source (rough Haversine approx)
            dlat = (lat - source_lat) * 111_000
            dlon = (lon - source_lon) * 111_000 * math.cos(math.radians(source_lat))
            distance_m = math.sqrt(dlat**2 + dlon**2)

            targets.append({
                "lat": lat,
                "lon": lon,
                "elevation": elev,
                "depth": round(depth, 3),
                "distance_m": round(distance_m, 1),
            })

    # Sort by distance (closest cells flood first)
    targets.sort(key=lambda t: t["distance_m"])
    return targets


def _build_flood_polygon(center_lat: float, center_lon: float,
                         flood_targets: list, base_radius_deg: float) -> dict:
    """
    Build a GeoJSON polygon encompassing the flooded area.

    Uses the convex hull of flooded DEM cells, or falls back to a
    buffered circle if too few cells are found.

    Args:
        center_lat: Centre of flood origin.
        center_lon: Centre of flood origin.
        flood_targets: List of flooded cell dicts.
        base_radius_deg: Minimum polygon radius.

    Returns:
        GeoJSON Polygon geometry dict.
    """
    if len(flood_targets) >= 3:
        # Build convex hull from flooded cells
        points = [(t["lon"], t["lat"]) for t in flood_targets]
        # Add centre point
        points.append((center_lon, center_lat))

        # Simple convex hull using gift wrapping
        hull = _convex_hull(points)
        # Close the ring
        if hull[0] != hull[-1]:
            hull.append(hull[0])

        return {
            "type": "Polygon",
            "coordinates": [hull],
        }
    else:
        # Fallback: circular buffer
        radius = max(base_radius_deg, 0.005)
        num_points = 32
        ring = []
        for i in range(num_points + 1):
            angle = 2 * math.pi * i / num_points
            ring.append([
                round(center_lon + radius * math.cos(angle), 6),
                round(center_lat + radius * math.sin(angle), 6),
            ])
        return {
            "type": "Polygon",
            "coordinates": [ring],
        }


def _convex_hull(points: list) -> list:
    """Compute convex hull of 2D points using Andrew's monotone chain."""
    points = sorted(set(points))
    if len(points) <= 1:
        return points

    # Build lower hull
    lower = []
    for p in points:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    # Build upper hull
    upper = []
    for p in reversed(points):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def _cross(o, a, b):
    """2D cross product of vectors OA and OB."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def simulate_flood_propagation(conn, flood_polygons: dict,
                               propagation_steps: int = MAX_PROPAGATION_STEPS) -> dict:
    """
    Simulate flood propagation using real DEM terrain data.

    For each Phase 3 flood polygon:
      1. Extract centroid and water surface elevation
      2. Query nearby DEM cells
      3. Identify cells below water surface (they flood)
      4. Iteratively expand downstream with depth decay
      5. Build predicted flood polygon geometry

    Args:
        conn: psycopg2 PostGIS connection.
        flood_polygons: GeoJSON FeatureCollection from Phase 3 flood_layer.
        propagation_steps: Number of expansion iterations.

    Returns:
        GeoJSON FeatureCollection of predicted flood zones.
    """
    features = flood_polygons.get("features", [])
    if not features:
        logger.info("No flood polygons to propagate")
        return {"type": "FeatureCollection", "features": []}

    predicted_features = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for i, feature in enumerate(features):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})

        submergence_ratio = props.get("submergence_ratio", 0.0)
        water_surface_elev = props.get("water_surface_elevation", 0.0)
        severity = props.get("severity", "moderate")

        # Get centroid of flood polygon
        coords = geom.get("coordinates", [[]])
        if geom.get("type") == "Polygon" and coords and coords[0]:
            ring = coords[0]
            center_lat = sum(c[1] for c in ring) / len(ring)
            center_lon = sum(c[0] for c in ring) / len(ring)
        else:
            continue

        logger.info(
            "Propagating flood %d: centre=(%.4f, %.4f) WSE=%.2f sub_ratio=%.2f",
            i, center_lat, center_lon, water_surface_elev, submergence_ratio
        )

        # Query DEM around the flood zone
        dem_points = _query_dem_grid(conn, center_lat, center_lon)

        if not dem_points:
            logger.warning("No DEM data near (%.4f, %.4f) — using buffer fallback",
                           center_lat, center_lon)
            # Fallback: expand by submergence ratio
            radius_deg = 0.005 + submergence_ratio * 0.015
            predicted_features.append({
                "type": "Feature",
                "geometry": _build_flood_polygon(
                    center_lat, center_lon, [], radius_deg
                ),
                "properties": {
                    "submergence_ratio": round(submergence_ratio * DEPTH_DECAY_FACTOR, 4),
                    "severity": severity,
                    "timestamp": timestamp,
                    "source": "phase4_predicted",
                    "propagation_step": 1,
                },
            })
            continue

        # Iterative propagation with depth decay
        current_wse = water_surface_elev
        all_flood_targets = []

        for step in range(propagation_steps):
            targets = _compute_flow_targets(
                dem_points, current_wse, center_lat, center_lon
            )
            if not targets:
                break

            all_flood_targets.extend(targets)

            # Decay water surface for next iteration
            current_wse *= DEPTH_DECAY_FACTOR
            if current_wse < MIN_DEPTH_THRESHOLD:
                break

        if all_flood_targets:
            # Compute predicted submergence from average depth
            avg_depth = sum(t["depth"] for t in all_flood_targets) / len(all_flood_targets)
            pred_submergence = min(1.0, avg_depth / 3.0)  # normalise by 3m max

            max_distance = max(t["distance_m"] for t in all_flood_targets)
            base_radius = max(0.005, max_distance / 111_000)

            predicted_features.append({
                "type": "Feature",
                "geometry": _build_flood_polygon(
                    center_lat, center_lon, all_flood_targets, base_radius
                ),
                "properties": {
                    "submergence_ratio": round(pred_submergence, 4),
                    "severity": severity,
                    "timestamp": timestamp,
                    "source": "phase4_predicted",
                    "propagation_step": min(step + 1, propagation_steps),
                    "cells_flooded": len(all_flood_targets),
                    "max_distance_m": max_distance,
                },
            })

    logger.info("Flood propagation complete: %d predicted zones from %d source polygons",
                len(predicted_features), len(features))

    return {
        "type": "FeatureCollection",
        "features": predicted_features,
    }
