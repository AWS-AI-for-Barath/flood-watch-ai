"""
lambda_handler.py — AWS Lambda + API Gateway wrapper for the routing API.

Parses ``start`` and ``goal`` query parameters, delegates to
``routing_api.handle_route_request()``, and returns a structured
JSON envelope consistent with the project's existing Lambda handler
pattern (see ``src/lambda_handler.py``).

Expected API Gateway query:
    GET /route?start=13.08,80.27&goal=12.95,80.22
"""

import json
import logging
import os
import traceback

logger = logging.getLogger(__name__)


def _parse_coord(value: str) -> tuple[float, float]:
    """Parse 'lat,lon' string to (lat, lon) tuple."""
    parts = value.strip().split(",")
    if len(parts) != 2:
        raise ValueError(f"Expected 'lat,lon', got '{value}'")
    return (float(parts[0]), float(parts[1]))


def handler(event, context):
    """
    AWS Lambda entrypoint for the routing API.

    Invoked via API Gateway HTTP API (v2 payload format).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        # Parse query parameters
        params = event.get("queryStringParameters") or {}
        raw_start = params.get("start", "")
        raw_goal = params.get("goal", "")

        if not raw_start or not raw_goal:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "status": "error",
                    "message": "Missing required query parameters: start, goal "
                               "(format: lat,lon)",
                }),
            }

        start = _parse_coord(raw_start)
        goal = _parse_coord(raw_goal)

        # Determine OSRM mode
        use_mock = os.environ.get("OSRM_MOCK", "0") == "1"

        # Route
        from phase4_routing.routing.routing_api import handle_route_request

        result = handle_route_request(
            start=start,
            goal=goal,
            use_mock_osrm=use_mock,
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(result),
        }

    except ValueError as e:
        logger.error("Invalid parameters: %s", e)
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "error",
                "message": f"Invalid parameters: {e}",
            }),
        }

    except Exception as e:
        logger.error("Unhandled error: %s\n%s", e, traceback.format_exc())
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "error",
                "message": "Internal server error",
            }),
        }
