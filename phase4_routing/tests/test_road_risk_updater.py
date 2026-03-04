"""
test_road_risk_updater.py — Tests for road risk computation and update engine.

Validates:
  - Weight computation for all four submergence tiers
  - Road closure logic for ratio > 0.7
  - Spatial intersection with mock geometries
  - End-to-end update flow with mock DB
"""

import math
import os

import pytest
from shapely.geometry import LineString, Polygon

# Ensure mock DB mode
os.environ["FLOODWATCH_DB_MODE"] = "mock"

from phase4_routing.db.connection import reset_mock_connection
from phase4_routing.routing.risk_levels import (
    MULTIPLIER_CLOSED,
    MULTIPLIER_HIGH,
    MULTIPLIER_LOW,
    MULTIPLIER_MODERATE,
    compute_weight,
    get_risk_level,
    is_road_closed,
)
from phase4_routing.routing.road_risk_updater import (
    intersect_road_with_floods,
    update_road_risks,
)


class TestComputeWeight:
    """Weight computation for all submergence tiers."""

    def test_low_submergence(self):
        """< 0.2 should return base weight × 1."""
        assert compute_weight(1.0, 0.1) == 1.0 * MULTIPLIER_LOW
        assert compute_weight(2.0, 0.0) == 2.0 * MULTIPLIER_LOW
        assert compute_weight(1.0, 0.19) == 1.0 * MULTIPLIER_LOW

    def test_moderate_submergence(self):
        """0.2 – 0.4 should return base weight × 2."""
        assert compute_weight(1.0, 0.3) == 1.0 * MULTIPLIER_MODERATE
        assert compute_weight(2.0, 0.25) == 2.0 * MULTIPLIER_MODERATE

    def test_high_submergence(self):
        """0.4 – 0.7 should return base weight × 5."""
        assert compute_weight(1.0, 0.5) == 1.0 * MULTIPLIER_HIGH
        assert compute_weight(2.0, 0.65) == 2.0 * MULTIPLIER_HIGH

    def test_severe_submergence_closed(self):
        """> 0.7 should return infinity (road closed)."""
        assert compute_weight(1.0, 0.8) == MULTIPLIER_CLOSED
        assert math.isinf(compute_weight(1.0, 0.8))
        assert math.isinf(compute_weight(1.0, 1.0))

    def test_boundary_at_0_2(self):
        """Exactly 0.2 is still 'low' tier (not moderate)."""
        assert compute_weight(1.0, 0.2) == MULTIPLIER_LOW

    def test_boundary_at_0_4(self):
        """Exactly 0.4 is still 'moderate' tier (not high)."""
        assert compute_weight(1.0, 0.4) == MULTIPLIER_MODERATE

    def test_boundary_at_0_7(self):
        """Exactly 0.7 is still 'high' tier (not closed)."""
        assert compute_weight(1.0, 0.7) == MULTIPLIER_HIGH


class TestRiskLevel:
    """Risk level label mapping."""

    def test_low(self):
        assert get_risk_level(0.1) == "low"

    def test_moderate(self):
        assert get_risk_level(0.3) == "moderate"

    def test_high(self):
        assert get_risk_level(0.5) == "high"

    def test_severe(self):
        assert get_risk_level(0.8) == "severe"


class TestIsRoadClosed:
    """Road closure detection."""

    def test_not_closed(self):
        assert is_road_closed(0.5) is False

    def test_closed(self):
        assert is_road_closed(0.8) is True

    def test_boundary(self):
        assert is_road_closed(0.7) is False
        assert is_road_closed(0.71) is True


class TestIntersectRoadWithFloods:
    """Spatial intersection logic."""

    def test_no_intersection(self):
        """Road outside all flood polygons → 0.0."""
        road = LineString([(0, 0), (1, 0)])
        floods = [{
            "geometry": Polygon([(10, 10), (11, 10), (11, 11), (10, 11)]),
            "submergence_ratio": 0.5,
        }]
        assert intersect_road_with_floods(road, floods) == 0.0

    def test_full_intersection(self):
        """Road fully inside polygon → polygon's submergence_ratio."""
        road = LineString([(0.2, 0.2), (0.8, 0.8)])
        floods = [{
            "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            "submergence_ratio": 0.6,
        }]
        assert intersect_road_with_floods(road, floods) == 0.6

    def test_max_of_multiple_polygons(self):
        """When multiple flood zones overlap, take the max ratio."""
        road = LineString([(0.5, 0.5), (0.5, 1.5)])
        floods = [
            {
                "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                "submergence_ratio": 0.3,
            },
            {
                "geometry": Polygon([(0, 1), (1, 1), (1, 2), (0, 2)]),
                "submergence_ratio": 0.7,
            },
        ]
        assert intersect_road_with_floods(road, floods) == 0.7

    def test_empty_floods(self):
        """No flood polygons → 0.0."""
        road = LineString([(0, 0), (1, 0)])
        assert intersect_road_with_floods(road, []) == 0.0


class TestUpdateRoadRisks:
    """End-to-end road risk update with mock DB."""

    def setup_method(self):
        reset_mock_connection()

    def test_no_predictions_returns_zeros(self):
        """With no flood predictions, summary should be all zeros."""
        result = update_road_risks(road_segments=[])
        assert result["updated"] == 0
        assert result["closed"] == 0

    def test_update_with_mock_segments(self):
        """Segments with flood data should be updated."""
        from phase4_routing.db.flood_store import store_predictions

        # Store a flood prediction
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[(80.2, 13.0), (80.3, 13.0),
                                     (80.3, 13.1), (80.2, 13.1),
                                     (80.2, 13.0)]],
                },
                "properties": {
                    "submergence_ratio": 0.6,
                    "velocity": 1.2,
                    "timestamp": "2099-12-31T00:00:00+00:00",
                },
            }],
        }
        store_predictions(geojson)

        # Define a road segment that intersects
        segments = [{
            "road_segment_id": "road_001",
            "geometry": {
                "type": "LineString",
                "coordinates": [(80.25, 13.05), (80.28, 13.08)],
            },
            "base_weight": 1.0,
        }]

        result = update_road_risks(
            road_segments=segments,
            prediction_window_minutes=999999,
        )

        assert result["updated"] == 1
        assert result["flood_polygons"] >= 1
