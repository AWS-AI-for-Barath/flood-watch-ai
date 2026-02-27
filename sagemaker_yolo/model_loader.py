"""
model_loader.py — Load YOLO flood detection model with mock fallback.

Used by the SageMaker inference entrypoint to obtain a model object.
If the trained weights file exists, loads via Ultralytics YOLO.
Otherwise, returns a lightweight mock that produces synthetic detections
so the inference chain works end-to-end without real weights.
"""

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)


class MockModel:
    """
    Lightweight stand-in for a YOLO model.

    Returns a single synthetic detection so downstream code
    (predict.py, inference.py, test_local.py) can run without
    trained weights.
    """

    class _MockBox:
        """Mimics ultralytics Boxes for a single detection."""

        def __init__(self):
            self.xyxy = np.array([[120.0, 80.0, 400.0, 300.0]])
            self.conf = np.array([0.85])
            self.cls = np.array([2])  # COCO class 2 = car

    class _MockResult:
        """Mimics a single ultralytics Result object."""

        def __init__(self):
            self.boxes = MockModel._MockBox()
            self.names = {
                0: "person",
                1: "bicycle",
                2: "car",
                3: "motorcycle",
                5: "bus",
                7: "truck",
            }

    def __call__(self, image, **kwargs):
        """Return a list containing one mock result."""
        logger.info("MockModel: generating synthetic detection")
        return [self._MockResult()]

    @property
    def names(self):
        return {
            0: "person",
            1: "bicycle",
            2: "car",
            3: "motorcycle",
            5: "bus",
            7: "truck",
        }


def load_model(model_path: str):
    """
    Load a YOLO model from *model_path*.

    Args:
        model_path: Absolute or relative path to the ``.pt`` weights file.

    Returns:
        A YOLO model instance (real or mock).

    Behaviour:
        - If the file exists → load via ``ultralytics.YOLO``.
        - Otherwise → return a ``MockModel`` that produces synthetic
          detections so the rest of the pipeline can be exercised.
    """
    if os.path.isfile(model_path):
        try:
            from ultralytics import YOLO

            model = YOLO(model_path)
            logger.info("Loaded real YOLO model from: %s", model_path)
            return model
        except Exception as exc:
            logger.warning(
                "Failed to load YOLO model from %s: %s — falling back to mock",
                model_path,
                exc,
            )

    logger.info(
        "Model file not found at %s — using MockModel for inference",
        model_path,
    )
    return MockModel()
