"""Tests for src/yolo_detector.py — YOLO detection and submergence estimation."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.yolo_detector import (
    COCO_MODEL_PATH,
    DEFAULT_SUBMERGENCE_RATIO,
    FLOOD_MODEL_FALLBACK,
    FLOOD_MODEL_PATH,
    REFERENCE_HEIGHTS_CM,
    estimate_depth,
    _resolve_model_path,
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
    """Test submergence estimation logic."""

    @patch("src.yolo_detector.YOLO")
    def test_car_detection(self, mock_yolo_cls):
        """Should estimate submergence using a detected car."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # class_id=2 is car, confidence=0.9, box from (100,200) to (300,400)
        mock_result = _make_mock_result(2, 0.9, [100, 200, 300, 400])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame)

        assert result["submergence_ratio"] is not None
        assert 0.0 <= result["submergence_ratio"] <= 1.0
        assert result["reference_object"] == "car"
        assert result["confidence"] == 0.9

    @patch("src.yolo_detector.YOLO")
    def test_person_detection(self, mock_yolo_cls):
        """Should estimate submergence using a detected person."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = _make_mock_result(0, 0.85, [200, 100, 280, 450])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame)

        assert result["submergence_ratio"] is not None
        assert 0.0 <= result["submergence_ratio"] <= 1.0
        assert result["reference_object"] == "person"

    @patch("src.yolo_detector.YOLO")
    def test_deeper_object_higher_submergence(self, mock_yolo_cls):
        """Object near bottom of frame should have higher submergence."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Object near bottom (y2=470 out of 480)
        mock_result_low = _make_mock_result(2, 0.9, [100, 350, 300, 470])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result_low]
        mock_yolo_cls.return_value = mock_model

        result_low = estimate_depth(frame)

        # Object near top (y2=200 out of 480)
        mock_result_high = _make_mock_result(2, 0.9, [100, 50, 300, 200])
        mock_model.return_value = [mock_result_high]

        result_high = estimate_depth(frame)

        assert result_low["submergence_ratio"] > result_high["submergence_ratio"]

    @patch("src.yolo_detector.YOLO")
    def test_no_detections(self, mock_yolo_cls):
        """Should return nulls when no reference objects are detected."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = MagicMock()
        mock_result.boxes = MagicMock()
        mock_result.boxes.__len__ = lambda self: 0
        mock_result.boxes.cls = []
        mock_result.boxes.conf = []
        mock_result.boxes.xyxy = []

        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame)

        assert result["submergence_ratio"] is None
        assert result["reference_object"] is None
        assert result["confidence"] is None

    @patch("src.yolo_detector.YOLO")
    def test_low_confidence_filtered(self, mock_yolo_cls):
        """Should ignore detections below the default confidence threshold (0.4)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = _make_mock_result(2, 0.35, [100, 200, 300, 400])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame)

        assert result["submergence_ratio"] is None

    @patch("src.yolo_detector.YOLO")
    def test_custom_confidence_threshold(self, mock_yolo_cls):
        """Should accept custom confidence threshold parameter."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = _make_mock_result(2, 0.35, [100, 200, 300, 400])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame, confidence_threshold=0.3)
        assert result["submergence_ratio"] is not None
        assert result["reference_object"] == "car"

    @patch("src.yolo_detector.YOLO")
    def test_override_submergence_ratio(self, mock_yolo_cls):
        """Should use explicit submergence_ratio when provided."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = _make_mock_result(2, 0.9, [100, 200, 300, 400])
        mock_model = MagicMock()
        mock_model.return_value = [mock_result]
        mock_yolo_cls.return_value = mock_model

        result = estimate_depth(frame, submergence_ratio=0.75)
        assert result["submergence_ratio"] == 0.75

    @patch("src.yolo_detector.YOLO")
    def test_model_failure(self, mock_yolo_cls):
        """Should return fallback on model failure."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_yolo_cls.side_effect = Exception("Model load failed")

        result = estimate_depth(frame)

        assert result["submergence_ratio"] is None


class TestModelResolution:
    """Test the 3-tier model fallback chain."""

    def test_model_path_constants(self):
        """Verify model path constants are correctly defined."""
        assert "yolov8_flood_highacc.pt" in FLOOD_MODEL_PATH
        assert "yolov8_flood.pt" in FLOOD_MODEL_FALLBACK
        assert COCO_MODEL_PATH == "yolov8s.pt"

    @patch("os.path.isfile")
    def test_fallback_to_coco(self, mock_isfile):
        """Should fall back to COCO when no flood models exist."""
        mock_isfile.return_value = False

        result = _resolve_model_path()
        assert result == COCO_MODEL_PATH

    @patch("os.path.isfile")
    def test_highacc_model_priority(self, mock_isfile):
        """Should prefer high-accuracy model when it exists."""
        def isfile_side_effect(path):
            return "highacc" in path

        mock_isfile.side_effect = isfile_side_effect

        result = _resolve_model_path()
        assert result == FLOOD_MODEL_PATH

    @patch("os.path.isfile")
    def test_fallback_to_baseline(self, mock_isfile):
        """Should fall back to baseline flood model when highacc is missing."""
        def isfile_side_effect(path):
            return "yolov8_flood.pt" in path and "highacc" not in path

        mock_isfile.side_effect = isfile_side_effect

        result = _resolve_model_path()
        assert result == FLOOD_MODEL_FALLBACK

    @patch("os.path.isfile")
    def test_explicit_model_path(self, mock_isfile):
        """Should use explicitly provided model path if file exists."""
        mock_isfile.return_value = True

        result = _resolve_model_path("/custom/path/model.pt")
        assert result == "/custom/path/model.pt"

    def test_default_confidence_threshold(self):
        """Default confidence threshold should be 0.4 for higher precision."""
        import inspect
        sig = inspect.signature(estimate_depth)
        default = sig.parameters["confidence_threshold"].default
        assert default == 0.4

    def test_api_backwards_compatible(self):
        """estimate_depth API should have the expected parameters."""
        import inspect
        sig = inspect.signature(estimate_depth)
        params = list(sig.parameters.keys())
        assert "frame" in params
        assert "model_path" in params
        assert "submergence_ratio" in params
        assert "confidence_threshold" in params
