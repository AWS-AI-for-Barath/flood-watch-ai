"""
osrm_client.py — HTTP client for the OSRM routing engine.

Provides a clean interface to query the OSRM backend running on
EC2.  Includes a ``MockOSRMClient`` for local testing that returns
synthetic routes without requiring a live OSRM instance.
"""

import json
import logging
import math
import os
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "http://localhost:5000"


class OSRMClient:
    """
    HTTP client for OSRM /route/v1/driving endpoint.

    Args:
        endpoint: Base URL of the OSRM backend
                  (e.g. ``http://ec2-ip:5000``).
    """

    def __init__(self, endpoint: str | None = None):
        self.endpoint = (
            endpoint
            or os.environ.get("OSRM_ENDPOINT", DEFAULT_ENDPOINT)
        ).rstrip("/")

    def get_route(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
    ) -> dict:
        """
        Query OSRM for a route between two points.

        Args:
            start: (latitude, longitude) of origin.
            goal:  (latitude, longitude) of destination.

        Returns:
            Dict with ``route`` (list of [lat, lon] waypoints),
            ``distance`` (metres), ``duration`` (seconds), and
            ``status`` ("ok" or "error").
        """
        # OSRM uses lon,lat ordering
        coords = f"{start[1]},{start[0]};{goal[1]},{goal[0]}"
        url = (
            f"{self.endpoint}/route/v1/driving/{coords}"
            f"?geometries=geojson&overview=full&alternatives=false"
        )

        logger.info("OSRM request: %s", url)

        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (URLError, OSError) as e:
            logger.error("OSRM connection failed: %s", e)
            return {
                "status": "error",
                "message": f"OSRM unavailable: {e}",
                "route": [],
                "distance": 0,
                "duration": 0,
            }

        if data.get("code") != "Ok" or not data.get("routes"):
            return {
                "status": "error",
                "message": data.get("message", "No route found"),
                "route": [],
                "distance": 0,
                "duration": 0,
            }

        route = data["routes"][0]
        # Convert from GeoJSON [lon, lat] → [lat, lon]
        coordinates = [
            [coord[1], coord[0]]
            for coord in route["geometry"]["coordinates"]
        ]

        return {
            "status": "ok",
            "route": coordinates,
            "distance": route["distance"],
            "duration": route["duration"],
        }


class MockOSRMClient:
    """
    Mock OSRM client for testing.

    Returns a synthetic straight-line route between start and goal
    with realistic-looking intermediate waypoints.
    """

    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint or "mock://osrm"

    def get_route(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
    ) -> dict:
        """Return a synthetic route between start and goal."""
        num_points = 10
        route = []

        for i in range(num_points + 1):
            t = i / num_points
            lat = start[0] + t * (goal[0] - start[0])
            lon = start[1] + t * (goal[1] - start[1])
            # Add slight curve for realism
            offset = 0.002 * math.sin(t * math.pi)
            route.append([round(lat + offset, 6), round(lon - offset, 6)])

        # Approximate distance using Haversine
        distance = self._haversine(start, goal)

        return {
            "status": "ok",
            "route": route,
            "distance": distance,
            "duration": distance / 10.0,  # ~36 km/h average
        }

    @staticmethod
    def _haversine(p1: tuple, p2: tuple) -> float:
        """Haversine distance in metres between two (lat, lon) points."""
        R = 6371000
        lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
        lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_osrm_client(mock: bool = False) -> OSRMClient | MockOSRMClient:
    """
    Factory function: returns the appropriate OSRM client.

    Args:
        mock: If True (or env ``OSRM_MOCK=1``), return MockOSRMClient.
    """
    if mock or os.environ.get("OSRM_MOCK", "0") == "1":
        logger.info("Using MockOSRMClient")
        return MockOSRMClient()
    return OSRMClient()
