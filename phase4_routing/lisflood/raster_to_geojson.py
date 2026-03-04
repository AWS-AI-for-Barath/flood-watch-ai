"""
raster_to_geojson.py — Lambda function: raster → flood polygon GeoJSON.

Reads flood depth + velocity rasters from S3, thresholds depth values
to extract flood polygons (contour-based), and produces a GeoJSON
FeatureCollection matching the Phase 3 schema contract:

    {
      "type": "FeatureCollection",
      "features": [{
        "geometry": Polygon,
        "properties": {
          "submergence_ratio": float,
          "timestamp": ISO8601,
          "velocity": float
        }
      }]
    }

Results are stored in PostGIS via ``flood_store.store_predictions()``.
"""

import json
import logging
import os
from datetime import datetime, timezone

import numpy as np

logger = logging.getLogger(__name__)

# Depth threshold (metres) — pixels below this are not flooded
DEPTH_THRESHOLD = 0.1

# Maximum expected depth (metres) for normalising submergence_ratio
MAX_DEPTH = 3.0

# Chennai bounding box (must match mock_container.BBOX)
BBOX = {
    "min_lat": 12.90,
    "max_lat": 13.20,
    "min_lon": 80.15,
    "max_lon": 80.35,
}


def _pixel_to_coords(row: int, col: int, shape: tuple) -> tuple:
    """Convert pixel (row, col) to (lon, lat) using the BBOX."""
    rows, cols = shape
    lat = BBOX["max_lat"] - (row / rows) * (BBOX["max_lat"] - BBOX["min_lat"])
    lon = BBOX["min_lon"] + (col / cols) * (BBOX["max_lon"] - BBOX["min_lon"])
    return (lon, lat)


def _extract_flood_polygons(
    depth: np.ndarray,
    velocity: np.ndarray | None = None,
    threshold: float = DEPTH_THRESHOLD,
) -> list:
    """
    Extract flood polygons from depth raster using connected-component
    labelling and contour extraction.

    Each polygon gets:
      - submergence_ratio = mean(depth_in_region) / MAX_DEPTH, clamped [0,1]
      - velocity = mean velocity in region (if velocity raster provided)

    Args:
        depth:     2D float array of flood depths (metres).
        velocity:  Optional 2D float array of flow velocity (m/s).
        threshold: Minimum depth to consider flooded.

    Returns:
        List of (polygon_coords, submergence_ratio, mean_velocity) tuples.
    """
    from scipy import ndimage

    # Binary flood mask
    flood_mask = depth > threshold
    labelled, num_features = ndimage.label(flood_mask)

    polygons = []
    for region_id in range(1, num_features + 1):
        region_mask = labelled == region_id
        region_pixels = np.argwhere(region_mask)

        if len(region_pixels) < 4:
            continue  # need at least 4 points for a polygon

        # Compute bounding convex hull as polygon coordinates
        rows_idx = region_pixels[:, 0]
        cols_idx = region_pixels[:, 1]

        min_r, max_r = rows_idx.min(), rows_idx.max()
        min_c, max_c = cols_idx.min(), cols_idx.max()

        # Build rectangle from bounding box (simplified polygon)
        shape = depth.shape
        corners = [
            _pixel_to_coords(min_r, min_c, shape),
            _pixel_to_coords(min_r, max_c, shape),
            _pixel_to_coords(max_r, max_c, shape),
            _pixel_to_coords(max_r, min_c, shape),
            _pixel_to_coords(min_r, min_c, shape),  # close ring
        ]

        # Submergence ratio
        region_depths = depth[region_mask]
        submergence_ratio = float(
            np.clip(region_depths.mean() / MAX_DEPTH, 0.0, 1.0)
        )

        # Mean velocity
        mean_velocity = 0.0
        if velocity is not None:
            mean_velocity = float(velocity[region_mask].mean())

        polygons.append((corners, submergence_ratio, mean_velocity))

    return polygons


def rasters_to_geojson(
    depth: np.ndarray,
    velocity: np.ndarray | None = None,
    timestamp: str | None = None,
) -> dict:
    """
    Convert depth + velocity rasters into a GeoJSON FeatureCollection.

    Args:
        depth:     2D float array of flood depths.
        velocity:  Optional 2D velocity array.
        timestamp: ISO 8601 timestamp (auto-generated if None).

    Returns:
        GeoJSON FeatureCollection matching Phase 3 contract.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    polygons = _extract_flood_polygons(depth, velocity)

    features = []
    for coords, submergence_ratio, mean_velocity in polygons:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
            "properties": {
                "submergence_ratio": round(submergence_ratio, 4),
                "velocity": round(mean_velocity, 4),
                "timestamp": timestamp,
            },
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    logger.info(
        "Converted raster to GeoJSON: %d flood polygons extracted",
        len(features),
    )
    return geojson


def load_rasters_from_s3(bucket: str, prefix: str) -> tuple:
    """
    Load depth + velocity .npy rasters from S3.

    Args:
        bucket: S3 bucket name.
        prefix: S3 key prefix (e.g. ``lisflood/output/job-name/``).

    Returns:
        Tuple of (depth_array, velocity_array).
    """
    import io

    import boto3

    s3 = boto3.client("s3")

    depth_key = f"{prefix}flood_depth.npy"
    vel_key = f"{prefix}flood_velocity.npy"

    logger.info("Loading rasters from s3://%s/%s", bucket, prefix)

    depth_obj = s3.get_object(Bucket=bucket, Key=depth_key)
    depth = np.load(io.BytesIO(depth_obj["Body"].read()))

    velocity_obj = s3.get_object(Bucket=bucket, Key=vel_key)
    velocity = np.load(io.BytesIO(velocity_obj["Body"].read()))

    return depth, velocity


def load_rasters_from_local(directory: str) -> tuple:
    """Load depth + velocity .npy rasters from a local directory."""
    depth = np.load(os.path.join(directory, "flood_depth.npy"))
    velocity = np.load(os.path.join(directory, "flood_velocity.npy"))
    return depth, velocity


# ── Lambda handler ──────────────────────────────────────────────────
def lambda_handler(event, context):
    """
    AWS Lambda entrypoint — triggered by S3 event when LISFLOOD
    rasters are uploaded.
    """
    logging.basicConfig(level=logging.INFO)

    bucket = event["detail"]["bucket"]["name"]
    key = event["detail"]["object"]["key"]
    prefix = key.rsplit("/", 1)[0] + "/"

    logger.info("Raster upload detected: s3://%s/%s", bucket, key)

    depth, velocity = load_rasters_from_s3(bucket, prefix)
    geojson = rasters_to_geojson(depth, velocity)

    # Store in PostGIS
    from phase4_routing.db.flood_store import store_predictions

    store_predictions(geojson)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Raster converted and stored",
            "polygon_count": len(geojson["features"]),
        }),
    }
