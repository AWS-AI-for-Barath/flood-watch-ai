"""
test_local.py — End-to-end local test for Phase 4 routing pipeline.

Runs the complete pipeline locally without any AWS/OSRM/PostGIS:
  1. Generate mock LISFLOOD raster
  2. Convert raster → GeoJSON
  3. Store in mock DB
  4. Update road risks
  5. Query mock OSRM
  6. Return structured route response

Usage:
    python phase4_routing/tests/test_local.py
    # or
    python -m pytest phase4_routing/tests/test_local.py -v
"""

import json
import logging
import os
import sys

# Force mock mode
os.environ["FLOODWATCH_DB_MODE"] = "mock"
os.environ["OSRM_MOCK"] = "1"

from phase4_routing.db.connection import reset_mock_connection
from phase4_routing.db.flood_store import (
    get_latest_predictions,
    store_predictions,
)
from phase4_routing.lisflood.mock_container import (
    generate_mock_depth_raster,
    generate_mock_velocity_raster,
)
from phase4_routing.lisflood.raster_to_geojson import rasters_to_geojson
from phase4_routing.routing.road_risk_updater import update_road_risks
from phase4_routing.routing.routing_api import handle_route_request


def run_e2e_test():
    """Execute the full Phase 4 pipeline end-to-end."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("phase4_e2e")

    # Reset mock state
    reset_mock_connection()

    logger.info("=" * 60)
    logger.info("FloodWatch Phase 4 — End-to-End Local Test")
    logger.info("=" * 60)

    # ── Step 1: Generate mock LISFLOOD rasters ──────────────
    logger.info("[1/6] Generating mock LISFLOOD rasters...")
    depth = generate_mock_depth_raster(rows=50, cols=50, seed=42)
    velocity = generate_mock_velocity_raster(depth, seed=42)
    logger.info("  Depth shape: %s  range: [%.2f, %.2f]",
                depth.shape, depth.min(), depth.max())
    logger.info("  Velocity shape: %s  range: [%.2f, %.2f]",
                velocity.shape, velocity.min(), velocity.max())

    # ── Step 2: Convert raster → GeoJSON ────────────────────
    logger.info("[2/6] Converting rasters to GeoJSON...")
    geojson = rasters_to_geojson(depth, velocity)
    num_polygons = len(geojson["features"])
    logger.info("  Extracted %d flood polygons", num_polygons)

    # Validate Phase 3 schema compliance
    for feature in geojson["features"]:
        assert "submergence_ratio" in feature["properties"]
        assert "timestamp" in feature["properties"]
    logger.info("  ✓ Phase 3 schema compliance verified")

    # ── Step 3: Store in mock DB ────────────────────────────
    logger.info("[3/6] Storing predictions in mock DB...")
    stored = store_predictions(geojson)
    logger.info("  Stored %d predictions", stored)

    # Verify retrieval
    latest = get_latest_predictions(minutes=60)
    assert len(latest["features"]) == stored
    logger.info("  ✓ Predictions retrieved successfully")

    # ── Step 4: Update road risks ───────────────────────────
    logger.info("[4/6] Updating road risks...")
    road_segments = [
        {
            "road_segment_id": f"road_{i:03d}",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    (80.15 + i * 0.02, 12.95),
                    (80.15 + i * 0.02, 13.15),
                ],
            },
            "base_weight": 1.0,
        }
        for i in range(10)
    ]
    risk_summary = update_road_risks(
        road_segments=road_segments,
        prediction_window_minutes=60,
    )
    logger.info("  Updated: %d  Closed: %d  Flood polygons: %d",
                risk_summary["updated"], risk_summary["closed"],
                risk_summary["flood_polygons"])

    # ── Step 5: Query mock OSRM ─────────────────────────────
    logger.info("[5/6] Querying route via mock OSRM...")
    route_response = handle_route_request(
        start=(13.08, 80.27),
        goal=(12.95, 80.22),
        use_mock_osrm=True,
        prediction_window_minutes=60,
    )

    # ── Step 6: Validate response ───────────────────────────
    logger.info("[6/6] Validating route response...")
    required_keys = {
        "status", "start", "goal", "route",
        "risk_level", "max_submergence_ratio",
        "exposure_length", "predicted_arrival_risk",
    }
    assert required_keys.issubset(route_response.keys()), \
        f"Missing keys: {required_keys - route_response.keys()}"
    assert route_response["status"] in ("ok", "rerouted", "blocked")
    assert route_response["risk_level"] in ("low", "moderate", "high", "severe")
    assert len(route_response["route"]) > 0
    logger.info("  ✓ Response schema validated")

    # Pretty-print result
    logger.info("")
    logger.info("=" * 60)
    logger.info("ROUTE RESPONSE")
    logger.info("=" * 60)
    print(json.dumps(route_response, indent=2))

    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ END-TO-END TEST PASSED")
    logger.info("=" * 60)

    return route_response


# ── pytest entrypoint ───────────────────────────────────────────────

def test_e2e_pipeline():
    """Pytest wrapper for the end-to-end test."""
    result = run_e2e_test()
    assert result["status"] in ("ok", "rerouted", "blocked")
    assert len(result["route"]) > 0


# ── CLI entrypoint ──────────────────────────────────────────────────

if __name__ == "__main__":
    run_e2e_test()
