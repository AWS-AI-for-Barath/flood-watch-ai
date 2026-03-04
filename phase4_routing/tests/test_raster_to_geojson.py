"""
test_raster_to_geojson.py — Tests for raster → GeoJSON conversion.

Validates:
  - Synthetic rasters produce valid GeoJSON FeatureCollection
  - Output matches Phase 3 schema (submergence_ratio, timestamp)
  - Velocity field is attached
  - Depth thresholding works correctly
"""

import numpy as np
import pytest

from phase4_routing.lisflood.mock_container import (
    generate_mock_depth_raster,
    generate_mock_velocity_raster,
)
from phase4_routing.lisflood.raster_to_geojson import (
    DEPTH_THRESHOLD,
    rasters_to_geojson,
)


class TestRasterToGeoJSON:
    """Core conversion tests."""

    def setup_method(self):
        """Generate test rasters once per test."""
        self.depth = generate_mock_depth_raster(rows=50, cols=50, seed=42)
        self.velocity = generate_mock_velocity_raster(self.depth, seed=42)

    def test_output_is_feature_collection(self):
        """Returned dict must be a valid GeoJSON FeatureCollection."""
        result = rasters_to_geojson(self.depth, self.velocity)

        assert result["type"] == "FeatureCollection"
        assert isinstance(result["features"], list)

    def test_features_have_correct_schema(self):
        """Each feature must match the Phase 3 contract."""
        result = rasters_to_geojson(self.depth, self.velocity)

        for feature in result["features"]:
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert feature["geometry"]["type"] == "Polygon"

            props = feature["properties"]
            assert "submergence_ratio" in props
            assert "timestamp" in props
            assert isinstance(props["submergence_ratio"], float)
            assert 0.0 <= props["submergence_ratio"] <= 1.0

    def test_velocity_field_present(self):
        """Velocity should be attached to properties."""
        result = rasters_to_geojson(self.depth, self.velocity)

        for feature in result["features"]:
            assert "velocity" in feature["properties"]
            assert isinstance(feature["properties"]["velocity"], float)

    def test_custom_timestamp(self):
        """Custom timestamp should appear in all features."""
        ts = "2026-03-01T18:00:00Z"
        result = rasters_to_geojson(self.depth, self.velocity, timestamp=ts)

        for feature in result["features"]:
            assert feature["properties"]["timestamp"] == ts

    def test_polygon_coordinates_are_valid(self):
        """Polygon coordinates must form a closed ring with ≥4 points."""
        result = rasters_to_geojson(self.depth, self.velocity)

        for feature in result["features"]:
            coords = feature["geometry"]["coordinates"][0]
            assert len(coords) >= 4
            # Ring must be closed
            assert coords[0] == coords[-1]

    def test_zero_depth_produces_no_features(self):
        """An all-zero depth raster should yield no flood polygons."""
        zero_depth = np.zeros((50, 50), dtype=np.float32)
        result = rasters_to_geojson(zero_depth)

        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 0

    def test_uniform_flood_produces_features(self):
        """A uniformly flooded raster should produce at least one polygon."""
        flooded = np.full((50, 50), 1.5, dtype=np.float32)
        result = rasters_to_geojson(flooded)

        assert len(result["features"]) >= 1

    def test_submergence_ratio_clamped(self):
        """Submergence ratio must be 0–1 even for extreme depth values."""
        extreme = np.full((50, 50), 100.0, dtype=np.float32)
        result = rasters_to_geojson(extreme)

        for feature in result["features"]:
            ratio = feature["properties"]["submergence_ratio"]
            assert 0.0 <= ratio <= 1.0

    def test_none_velocity_handled(self):
        """Conversion should work without velocity raster."""
        result = rasters_to_geojson(self.depth, velocity=None)

        assert result["type"] == "FeatureCollection"
        for feature in result["features"]:
            assert feature["properties"]["velocity"] == 0.0
