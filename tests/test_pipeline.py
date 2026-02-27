"""Tests for src/pipeline.py — full fusion pipeline."""

import json
from unittest.mock import patch

import numpy as np
import pytest

from src.pipeline import run_pipeline


MOCK_NOVA_RESULT = {
    "people_trapped": False,
    "vehicles_submerged": True,
    "infrastructure_damage": False,
    "severity": "high",
    "description": "Severe flooding with submerged vehicles.",
}

MOCK_YOLO_RESULT = {
    "submergence_ratio": 0.5,
    "reference_object": "car",
    "confidence": 0.91,
}


class TestRunPipeline:
    """Test the fused pipeline output."""

    @patch("src.pipeline.estimate_depth", return_value=MOCK_YOLO_RESULT)
    @patch("src.pipeline.analyze_flood_scene", return_value=MOCK_NOVA_RESULT)
    @patch("src.pipeline.extract_frame")
    def test_full_pipeline(self, mock_extract, mock_nova, mock_yolo, tmp_path):
        """Should fuse Nova + YOLO into the expected JSON schema."""
        mock_extract.return_value = np.zeros((480, 640, 3), dtype=np.uint8)

        img_path = str(tmp_path / "flood.jpg")
        # Create a dummy file so the path looks valid in output
        with open(img_path, "w") as f:
            f.write("")

        result = run_pipeline(img_path)

        # Check all required keys exist
        required_keys = {
            "input_file", "submergence_ratio", "severity",
            "people_trapped", "vehicles_submerged", "infrastructure_damage",
            "reference_object", "confidence", "description",
        }
        assert set(result.keys()) == required_keys

        # Check values from mocks
        assert result["severity"] == "high"
        assert result["submergence_ratio"] == 0.5
        assert result["vehicles_submerged"] is True
        assert result["reference_object"] == "car"
        assert result["input_file"] == "flood.jpg"

    @patch("src.pipeline.estimate_depth", return_value=MOCK_YOLO_RESULT)
    @patch("src.pipeline.analyze_flood_scene", return_value=MOCK_NOVA_RESULT)
    @patch("src.pipeline.extract_frame")
    def test_writes_output_file(self, mock_extract, mock_nova, mock_yolo, tmp_path):
        """Should write result JSON to the specified output path."""
        mock_extract.return_value = np.zeros((480, 640, 3), dtype=np.uint8)

        img_path = str(tmp_path / "flood.jpg")
        with open(img_path, "w") as f:
            f.write("")

        output_path = str(tmp_path / "result.json")
        run_pipeline(img_path, output_path=output_path)

        assert (tmp_path / "result.json").exists()
        with open(output_path) as f:
            data = json.load(f)
        assert data["severity"] == "high"

    @patch("src.pipeline.estimate_depth", return_value=MOCK_YOLO_RESULT)
    @patch("src.pipeline.analyze_flood_scene", side_effect=RuntimeError("No credentials"))
    @patch("src.pipeline.extract_frame")
    def test_nova_failure_graceful(self, mock_extract, mock_nova, mock_yolo):
        """Should degrade gracefully when Nova is unavailable."""
        mock_extract.return_value = np.zeros((480, 640, 3), dtype=np.uint8)

        result = run_pipeline("dummy.jpg")

        assert result["severity"] == "unknown"
        assert "unavailable" in result["description"].lower()
        # YOLO results should still be present
        assert result["submergence_ratio"] == 0.5
