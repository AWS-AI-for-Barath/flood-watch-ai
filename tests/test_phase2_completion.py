"""Phase-2 completion tests for FloodWatch multimodal module."""

from unittest.mock import patch

import numpy as np
import pytest

from src.lambda_handler import handle_media_input
from src.pipeline import REQUIRED_KEYS, enforce_schema, run_pipeline
from src.validation import validate_depth_detection


# ---------- Mock data ----------

MOCK_NOVA = {
    "people_trapped": False,
    "vehicles_submerged": True,
    "infrastructure_damage": False,
    "severity": "high",
    "description": "Severe flooding with submerged vehicles.",
}

MOCK_YOLO_DEPTH = {
    "submergence_ratio": 0.5,
    "reference_object": "car",
    "confidence": 0.91,
}

MOCK_YOLO_NULL = {
    "submergence_ratio": None,
    "reference_object": None,
    "confidence": None,
}


# ---------- Depth detection ----------

class TestDepthDetection:
    """Validate submergence detection returns correct summary."""

    @patch("src.validation.run_pipeline")
    def test_depth_detected_scene(self, mock_pipeline):
        """Should report depth_detected=True when YOLO finds a reference object."""
        mock_pipeline.return_value = {
            **{"input_file": "flood.jpg"}, **MOCK_NOVA, **MOCK_YOLO_DEPTH
        }

        result = validate_depth_detection("flood.jpg")

        assert result["depth_detected"] is True
        assert result["reference_object"] == "car"
        assert result["submergence_ratio"] == 0.5

    @patch("src.validation.run_pipeline")
    def test_depth_null_scene(self, mock_pipeline):
        """Should report depth_detected=False when no reference objects."""
        mock_pipeline.return_value = {
            **{"input_file": "flood.jpg"}, **MOCK_NOVA, **MOCK_YOLO_NULL
        }

        result = validate_depth_detection("flood.jpg")

        assert result["depth_detected"] is False
        assert result["reference_object"] is None
        assert result["submergence_ratio"] is None


# ---------- Schema enforcement ----------

class TestSchemaEnforcement:
    """Verify enforce_schema produces a schema-locked output."""

    def test_schema_complete(self):
        """All required keys must be present in enforced output."""
        raw = {
            "input_file": "test.jpg",
            "submergence_ratio": 0.5,
            "severity": "medium",
            "people_trapped": False,
            "vehicles_submerged": True,
            "infrastructure_damage": False,
            "reference_object": "car",
            "confidence": 0.88,
            "description": "Test flood.",
        }
        result = enforce_schema(raw)
        assert set(result.keys()) == set(REQUIRED_KEYS.keys())

    def test_missing_keys_filled(self):
        """Missing optional fields should be filled with defaults."""
        result = enforce_schema({"input_file": "test.jpg"})
        assert result["submergence_ratio"] is None
        assert result["reference_object"] is None
        assert result["confidence"] is None
        assert result["severity"] == "unknown"

    def test_severity_enum_enforced(self):
        """Invalid severity values should be replaced with 'unknown'."""
        result = enforce_schema({
            "input_file": "x.jpg",
            "severity": "catastrophic",  # invalid
        })
        assert result["severity"] == "unknown"

    def test_valid_severities_accepted(self):
        """All valid severity values should pass through."""
        for sev in ("low", "medium", "high", "unknown"):
            result = enforce_schema({"input_file": "x.jpg", "severity": sev})
            assert result["severity"] == sev

    def test_no_extra_keys(self):
        """Extra keys should not leak into enforced output."""
        result = enforce_schema({
            "input_file": "x.jpg",
            "extra_key": "should_not_appear",
        })
        assert "extra_key" not in result


# ---------- Lambda wrapper structure ----------

class TestLambdaStructure:
    """Verify Lambda wrapper returns consistent envelope."""

    @patch("src.lambda_handler.run_pipeline")
    def test_lambda_success_structure(self, mock_pipeline):
        """Success response must have status=success, data dict, message=None."""
        mock_pipeline.return_value = {
            "input_file": "flood.jpg",
            "submergence_ratio": 0.5,
            "severity": "high",
            "people_trapped": False,
            "vehicles_submerged": True,
            "infrastructure_damage": False,
            "reference_object": "car",
            "confidence": 0.91,
            "description": "Flooding.",
        }

        result = handle_media_input("flood.jpg")

        assert result["status"] == "success"
        assert isinstance(result["data"], dict)
        assert result["message"] is None
        # Inner data should be schema-valid
        assert set(result["data"].keys()) == set(REQUIRED_KEYS.keys())

    @patch("src.lambda_handler.run_pipeline", side_effect=RuntimeError("Boom"))
    def test_lambda_error_structure(self, mock_pipeline):
        """Error response must have status=error, data=None, message populated."""
        result = handle_media_input("bad.jpg")

        assert result["status"] == "error"
        assert result["data"] is None
        assert isinstance(result["message"], str)
        assert "Boom" in result["message"]

    @patch("src.lambda_handler.run_pipeline", side_effect=Exception("unexpected"))
    def test_lambda_never_raises(self, mock_pipeline):
        """Lambda wrapper must never propagate exceptions."""
        result = handle_media_input("x.jpg")  # should not raise
        assert result["status"] == "error"
