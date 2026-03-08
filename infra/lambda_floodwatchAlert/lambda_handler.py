"""
processFloodAlerts -- Phase 5 Mass Alerting Lambda

Triggered by EventBridge (phase4_simulation_completed).

1. Fetches real users inside Phase 4 predicted flood polygons via
   PostGIS ST_Intersects (imported from alerting.user_store).
2. Generates multilingual SMS and Voice alert content.
3. Dispatches via Amazon Pinpoint and Amazon Polly.
4. Logs delivery status to DynamoDB with rate limiting.

Runtime: Python 3.12 | Memory: 512MB | Timeout: 60s
"""

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add parent directory to path so it can find `alerting`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alerting.alert_generator import process_flood_event
from alerting.dispatcher import dispatch_alerts


def handler(event, context=None):
    """
    Lambda entrypoint for processing flood alerts.

    Expected EventBridge payload (from Phase 4 completion):
        {
            "source": "floodwatch.phase4",
            "detail-type": "phase4_simulation_completed",
            "detail": {
                "flood_polygons": {
                    "type": "FeatureCollection",
                    "features": [...]
                }
            }
        }
    """
    logger.info("processFloodAlerts invoked: %s", json.dumps(event)[:200])

    try:
        # Default to production if not set locally
        os.environ.setdefault("FLOODWATCH_ALERT_MODE", "production")

        # 1. Extract flood polygons from event
        detail = event.get("detail", {})
        flood_polygons = detail.get("flood_polygons", {})
        
        features = flood_polygons.get("features", [])
        if not features:
            logger.info("No flood polygons provided in event. Exiting.")
            return _response(200, "No flood polygons to process.")

        # 2. Process flood event to generate alert payloads
        #    This queries PostGIS to find affected users and builds multilingual messages.
        logger.info("Processing %d flood polygons to find affected users...", len(features))
        alerts = process_flood_event(flood_polygons)

        if not alerts:
            logger.info("No users found inside the predicted flood zones.")
            return _response(200, "No users affected.")

        # 3. Dispatch alerts via Pinpoint/Polly and log to DynamoDB
        logger.info("Dispatching %d alerts...", len(alerts))
        summary = dispatch_alerts(alerts)

        return _response(200, "Alerts dispatched successfully", summary)

    except Exception as e:
        logger.error("processFloodAlerts FATAL ERROR: %s", e, exc_info=True)
        return _response(500, f"Internal Error: {str(e)}")


def _response(status_code: int, message: str, data: dict = None):
    body = {"status": "success" if status_code == 200 else "error", "message": message}
    if data:
        body.update(data)
    return {
        "statusCode": status_code,
        "body": json.dumps(body)
    }
