"""
simulateFloodPropagation — Phase 4 Propagation Lambda

Triggered after Phase 3 stores a new flood polygon (S3 event on
analysis/* prefix or direct invocation).

Reads observed flood polygons from Phase 3's ``flood_layer`` table,
runs DEM-aware flood propagation using real terrain data, and stores
predicted flood zones in the ``flood_prediction`` table.

Runtime: Python 3.12 | Memory: 512MB | Timeout: 60s

Environment Variables:
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS — RDS connection
    FLOODWATCH_DB_MODE  — production (default) | mock
    AWS_REGION          — AWS region (default: us-east-1)
"""

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add phase4_routing to path for Lambda packaging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def handler(event, context=None):
    """
    Lambda handler for flood propagation simulation.

    Can be triggered by:
    - S3 event (Phase 3 writes analysis JSON)
    - EventBridge schedule (periodic re-simulation)
    - Direct invocation (testing)

    Returns:
        Dict with statusCode and prediction count.
    """
    logger.info("simulateFloodPropagation invoked: %s",
                json.dumps(event, default=str)[:500])

    try:
        # Force production mode for DB connection
        os.environ.setdefault("FLOODWATCH_DB_MODE", "production")

        from phase4_routing.db.connection import get_connection
        from phase4_routing.db.flood_store import (
            fetch_phase3_flood_polygons,
            store_predictions,
        )
        from phase4_routing.lisflood.flood_propagation import (
            simulate_flood_propagation,
        )

        # 1. Get database connection
        conn = get_connection()
        logger.info("Connected to PostGIS")

        # 2. Fetch recent Phase 3 observed flood polygons
        phase3_floods = fetch_phase3_flood_polygons(minutes=60)
        source_count = len(phase3_floods.get("features", []))
        logger.info("Phase 3 source polygons: %d", source_count)

        if source_count == 0:
            logger.info("No Phase 3 flood polygons found — nothing to propagate")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "ok",
                    "message": "No source flood polygons",
                    "predictions_stored": 0,
                }),
            }

        # 3. Run DEM-aware flood propagation
        predicted = simulate_flood_propagation(conn, phase3_floods)
        predicted_features = predicted.get("features", [])
        logger.info("Flood propagation produced %d predicted zones",
                     len(predicted_features))

        # 4. Store predictions in flood_prediction table
        if predicted_features:
            stored_count = store_predictions(predicted)
            logger.info("Stored %d flood predictions in PostGIS", stored_count)
        else:
            stored_count = 0
            logger.info("No predicted zones generated — DEM may lack data")

        # 5. Close connection
        try:
            conn.close()
        except Exception:
            pass

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "ok",
                "source_polygons": source_count,
                "predictions_stored": stored_count,
            }),
        }

    except Exception as e:
        logger.error("simulateFloodPropagation FATAL: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e),
            }),
        }
