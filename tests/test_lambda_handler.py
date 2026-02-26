"""Tests for src/lambda_handler.py — Lambda wrapper."""

from unittest.mock import patch

import pytest

from src.lambda_handler import handle_media_input
from src.pipeline import REQUIRED_KEYS


MOCK_PIPELINE_OUTPUT = {
    "input_file": "flood.jpg",
    "water_depth_cm": 37.5,
    "severity": "high",
    "people_trapped": False,
    "vehicles_submerged": True,
    "infrastructure_damage": False,
    "reference_object": "car",
    "confidence": 0.91,
    "description": "Severe flooding with submerged vehicles.",
}


class TestHandleMediaInputSuccess:
    """Test successful pipeline execution through Lambda wrapper."""

    @patch("src.lambda_handler.run_pipeline", return_value=MOCK_PIPELINE_OUTPUT)
    def test_returns_success_status(self, mock_pipeline):
        """Should return status=success with pipeline data."""
        result = handle_media_input("flood.jpg")

        assert result["status"] == "success"
        assert isinstance(result["data"], dict)
        assert result["message"] is None

    @patch("src.lambda_handler.run_pipeline", return_value=MOCK_PIPELINE_OUTPUT)
    def test_data_is_schema_validated(self, mock_pipeline):
        """Data should be schema-validated with all required keys."""
        result = handle_media_input("flood.jpg")

        assert set(result["data"].keys()) == set(REQUIRED_KEYS.keys())
        assert result["data"]["severity"] == "high"
        assert result["data"]["water_depth_cm"] == 37.5

    @patch("src.lambda_handler.run_pipeline", return_value=MOCK_PIPELINE_OUTPUT)
    def test_passes_strategy_to_pipeline(self, mock_pipeline):
        """Should forward strategy parameter to run_pipeline."""
        handle_media_input("clip.mp4", strategy="first")

        mock_pipeline.assert_called_once_with(
            "clip.mp4", output_path=None, strategy="first"
        )

    @patch("src.lambda_handler.run_pipeline", return_value=MOCK_PIPELINE_OUTPUT)
    def test_passes_output_path_to_pipeline(self, mock_pipeline):
        """Should forward output_path to run_pipeline."""
        handle_media_input("flood.jpg", output_path="out.json")

        mock_pipeline.assert_called_once_with(
            "flood.jpg", output_path="out.json", strategy="middle"
        )


class TestHandleMediaInputError:
    """Test error handling — wrapper must never raise."""

    @patch("src.lambda_handler.run_pipeline", side_effect=FileNotFoundError("not found"))
    def test_file_not_found(self, mock_pipeline):
        """Should return status=error for missing files."""
        result = handle_media_input("missing.jpg")

        assert result["status"] == "error"
        assert "not found" in result["message"]
        assert result["data"] is None

    @patch("src.lambda_handler.run_pipeline", side_effect=ValueError("bad format"))
    def test_value_error(self, mock_pipeline):
        """Should return status=error for invalid input."""
        result = handle_media_input("bad.txt")

        assert result["status"] == "error"
        assert "ValueError" in result["message"]

    @patch("src.lambda_handler.run_pipeline", side_effect=RuntimeError("Bedrock down"))
    def test_runtime_error(self, mock_pipeline):
        """Should return status=error for runtime failures."""
        result = handle_media_input("flood.jpg")

        assert result["status"] == "error"
        assert "RuntimeError" in result["message"]

    @patch("src.lambda_handler.run_pipeline", side_effect=Exception("unexpected"))
    def test_generic_exception(self, mock_pipeline):
        """Should catch any exception and never raise."""
        result = handle_media_input("flood.jpg")

        assert result["status"] == "error"
        assert "unexpected" in result["message"]


class TestResponseSchema:
    """Verify the envelope structure — always 3 keys."""

    @patch("src.lambda_handler.run_pipeline", return_value=MOCK_PIPELINE_OUTPUT)
    def test_success_keys(self, mock_pipeline):
        """Success response should have status, data, and message."""
        result = handle_media_input("flood.jpg")
        assert set(result.keys()) == {"status", "data", "message"}

    @patch("src.lambda_handler.run_pipeline", side_effect=Exception("fail"))
    def test_error_keys(self, mock_pipeline):
        """Error response should have status, data, and message."""
        result = handle_media_input("flood.jpg")
        assert set(result.keys()) == {"status", "data", "message"}
