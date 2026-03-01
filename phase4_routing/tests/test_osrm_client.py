"""
test_osrm_client.py — Tests for the OSRM HTTP client.

Validates:
  - MockOSRMClient returns valid synthetic routes
  - Route coordinates are well-formed
  - Haversine distance calculation
  - Factory function respects env vars
"""

import os
import math

import pytest

from phase4_routing.osrm.osrm_client import (
    MockOSRMClient,
    OSRMClient,
    get_osrm_client,
)


class TestMockOSRMClient:
    """Mock client tests — no network required."""

    def setup_method(self):
        self.client = MockOSRMClient()

    def test_route_returns_ok(self):
        """Mock should always return status 'ok'."""
        result = self.client.get_route((13.08, 80.27), (12.95, 80.22))
        assert result["status"] == "ok"

    def test_route_has_coordinates(self):
        """Route should contain a list of [lat, lon] waypoints."""
        result = self.client.get_route((13.08, 80.27), (12.95, 80.22))
        route = result["route"]

        assert isinstance(route, list)
        assert len(route) >= 2

        for point in route:
            assert len(point) == 2
            assert isinstance(point[0], float)
            assert isinstance(point[1], float)

    def test_route_starts_near_origin(self):
        """First route point should be near the start coordinate."""
        start = (13.08, 80.27)
        result = self.client.get_route(start, (12.95, 80.22))

        first = result["route"][0]
        assert abs(first[0] - start[0]) < 0.01
        assert abs(first[1] - start[1]) < 0.01

    def test_route_ends_near_goal(self):
        """Last route point should be near the goal coordinate."""
        goal = (12.95, 80.22)
        result = self.client.get_route((13.08, 80.27), goal)

        last = result["route"][-1]
        assert abs(last[0] - goal[0]) < 0.01
        assert abs(last[1] - goal[1]) < 0.01

    def test_distance_is_positive(self):
        """Distance should be a positive number."""
        result = self.client.get_route((13.08, 80.27), (12.95, 80.22))
        assert result["distance"] > 0

    def test_duration_is_positive(self):
        """Duration should be a positive number."""
        result = self.client.get_route((13.08, 80.27), (12.95, 80.22))
        assert result["duration"] > 0

    def test_haversine_known_distance(self):
        """Haversine between known points should be reasonable."""
        # Chennai to nearby point (~15 km)
        dist = MockOSRMClient._haversine((13.08, 80.27), (12.95, 80.22))
        assert 10_000 < dist < 25_000  # 10–25 km range


class TestOSRMClientFactory:
    """Test the get_osrm_client factory function."""

    def test_mock_flag(self):
        """mock=True should return MockOSRMClient."""
        client = get_osrm_client(mock=True)
        assert isinstance(client, MockOSRMClient)

    def test_production_flag(self):
        """mock=False should return OSRMClient."""
        old = os.environ.pop("OSRM_MOCK", None)
        try:
            client = get_osrm_client(mock=False)
            assert isinstance(client, OSRMClient)
        finally:
            if old is not None:
                os.environ["OSRM_MOCK"] = old

    def test_env_var_override(self):
        """OSRM_MOCK=1 env var should return MockOSRMClient."""
        os.environ["OSRM_MOCK"] = "1"
        try:
            client = get_osrm_client()
            assert isinstance(client, MockOSRMClient)
        finally:
            os.environ["OSRM_MOCK"] = "0"
