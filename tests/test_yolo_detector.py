"""Tests for src/yolo_detector.py — YOLO detection and depth estimation."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.yolo_detector import (
    DEFAULT_WATERLINE_RATIO,
    REFERENCE_HEIGHTS_CM,
    estimate_depth,
)


def _make_mock_result(cls_id, conf, box_xyxy):
    """Create a mock YOLO result with a single detection."""
    import torch

    mock_boxes = MagicMock()
    mock_boxes.cls = torch.tensor([cls_id])
    mock_boxes.conf = torch.tensor([conf])
    mock_boxes.xyxy = torch.tensor([box_xyxy])
    mock_boxes.__len__ = lambda self: 1

    mock_result = MagicMock()
    mock_result.boxes = mock_boxes
    return mock_result


class TestEstimateDepth:
    """Test depth estimation logic."""

    @patch("src.yolo_detector.YOLO")
    def test_car_detection(self, mock_yolo_cls):
        """Should estimate depth using a detected car."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # class_id=2 is car, confidence=0.9, box from (100,200) to (300,400)
        mock_result = _make_mock_result(2, 0.9, [100, 200, 300, 400])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame)

        expected_depth = round(REFERENCE_HEIGHTS_CM["car"] * DEFAULT_WATERLINE_RATIO, 1)
        assert result["water_depth_cm"] == expected_depth
        assert result["reference_object"] == "car"
        assert result["confidence"] == 0.9

    @patch("src.yolo_detector.YOLO")
    def test_person_detection(self, mock_yolo_cls):
        """Should estimate depth using a detected person."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = _make_mock_result(0, 0.85, [200, 100, 280, 450])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame)

        expected_depth = round(REFERENCE_HEIGHTS_CM["person"] * DEFAULT_WATERLINE_RATIO, 1)
        assert result["water_depth_cm"] == expected_depth
        assert result["reference_object"] == "person"

    @patch("src.yolo_detector.YOLO")
    def test_no_detections(self, mock_yolo_cls):
        """Should return nulls when no reference objects are detected."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = MagicMock()
        mock_result.boxes = MagicMock()
        mock_result.boxes.__len__ = lambda self: 0
        # Simulate iteration over zero boxes
        mock_result.boxes.cls = []
        mock_result.boxes.conf = []
        mock_result.boxes.xyxy = []

        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame)

        assert result["water_depth_cm"] is None
        assert result["reference_object"] is None
        assert result["confidence"] is None

    @patch("src.yolo_detector.YOLO")
    def test_low_confidence_filtered(self, mock_yolo_cls):
        """Should ignore detections below confidence threshold."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Detection with very low confidence
        mock_result = _make_mock_result(2, 0.1, [100, 200, 300, 400])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame, confidence_threshold=0.3)

        assert result["water_depth_cm"] is None

    @patch("src.yolo_detector.YOLO")
    def test_model_failure(self, mock_yolo_cls):
        """Should return fallback on model failure."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_yolo_cls.side_effect = Exception("Model load failed")

        result = estimate_depth(frame)

        assert result["water_depth_cm"] is None
