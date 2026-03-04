"""
test_routing_api.py — Tests for the routing API endpoint.

Validates:
  - Full routing flow with mock OSRM + mock DB
  - Response schema (status, risk_level, route, etc.)
  - Blocked and rerouted scenarios
  - Lambda handler wrapper
"""

import json
import os

import pytest

# Force mock mode
os.environ["FLOODWATCH_DB_MODE"] = "mock"
os.environ["OSRM_MOCK"] = "1"

from phase4_routing.db.connection import reset_mock_connection
from phase4_routing.db.flood_store import store_predictions
from phase4_routing.routing.routing_api import handle_route_request


# ── Response schema keys ────────────────────────────────────────────

REQUIRED_KEYS = {
    "status", "start", "goal", "route",
    "risk_level", "max_submergence_ratio",
    "exposure_length", "predicted_arrival_risk",
}

VALID_STATUSES = {"ok", "rerouted", "blocked"}
VALID_RISK_LEVELS = {"low", "moderate", "high", "severe"}


class TestRoutingResponse:
    """Validate response structure and types."""

    def setup_method(self):
        reset_mock_connection()

    def test_response_has_all_keys(self):
        """All required keys should be present."""
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
        )
        assert REQUIRED_KEYS.issubset(result.keys())

    def test_status_is_valid(self):
        """Status must be ok, rerouted, or blocked."""
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
        )
        assert result["status"] in VALID_STATUSES

    def test_risk_level_is_valid(self):
        """Risk level must be one of the four tiers."""
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
        )
        assert result["risk_level"] in VALID_RISK_LEVELS

    def test_route_is_list_of_coordinates(self):
        """Route must be a list of [lat, lon] pairs."""
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
        )
        assert isinstance(result["route"], list)
        assert len(result["route"]) > 0
        for point in result["route"]:
            assert isinstance(point, list)
            assert len(point) == 2

    def test_numeric_fields_are_floats(self):
        """Numeric risk fields must be float."""
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
        )
        assert isinstance(result["max_submergence_ratio"], float)
        assert isinstance(result["exposure_length"], float)
        assert isinstance(result["predicted_arrival_risk"], float)

    def test_start_and_goal_preserved(self):
        """Start and goal coordinates should be preserved in response."""
        start = (13.08, 80.27)
        goal = (12.95, 80.22)
        result = handle_route_request(
            start=start, goal=goal, use_mock_osrm=True,
        )
        assert result["start"] == list(start)
        assert result["goal"] == list(goal)


class TestRoutingWithFloodData:
    """Test routing with active flood predictions."""

    def setup_method(self):
        reset_mock_connection()

    def _store_flood(self, submergence_ratio: float):
        """Helper: store a large flood polygon covering the Chennai area."""
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[(80.0, 12.8), (80.5, 12.8),
                                     (80.5, 13.2), (80.0, 13.2),
                                     (80.0, 12.8)]],
                },
                "properties": {
                    "submergence_ratio": submergence_ratio,
                    "velocity": 1.0,
                    "timestamp": "2099-12-31T00:00:00+00:00",
                },
            }],
        }
        store_predictions(geojson)

    def test_no_floods_returns_ok(self):
        """Without flood data, status should be 'ok' with low risk."""
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
        )
        assert result["status"] == "ok"
        assert result["risk_level"] == "low"
        assert result["max_submergence_ratio"] == 0.0

    def test_moderate_flood_returns_rerouted(self):
        """Moderate flood (0.2–0.7) should mark route as rerouted."""
        self._store_flood(0.45)
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
            prediction_window_minutes=999999,
        )
        assert result["status"] == "rerouted"
        assert result["max_submergence_ratio"] > 0.0

    def test_severe_flood_returns_blocked(self):
        """Severe flood (>0.7) should block the route."""
        self._store_flood(0.85)
        result = handle_route_request(
            start=(13.08, 80.27),
            goal=(12.95, 80.22),
            use_mock_osrm=True,
            prediction_window_minutes=999999,
        )
        assert result["status"] == "blocked"
        assert result["risk_level"] == "severe"


class TestLambdaHandler:
    """Test the Lambda wrapper."""

    def setup_method(self):
        reset_mock_connection()

    def test_lambda_success(self):
        from phase4_routing.routing.lambda_handler import handler

        event = {
            "queryStringParameters": {
                "start": "13.08,80.27",
                "goal": "12.95,80.22",
            }
        }
        result = handler(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert REQUIRED_KEYS.issubset(body.keys())

    def test_lambda_missing_params(self):
        from phase4_routing.routing.lambda_handler import handler

        event = {"queryStringParameters": {}}
        result = handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["status"] == "error"

    def test_lambda_invalid_coords(self):
        from phase4_routing.routing.lambda_handler import handler

        event = {
            "queryStringParameters": {
                "start": "invalid",
                "goal": "12.95,80.22",
            }
        }
        result = handler(event, None)

        assert result["statusCode"] == 400
