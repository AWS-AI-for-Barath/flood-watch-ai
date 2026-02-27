"""
inference.py — SageMaker-compatible entrypoint for YOLO flood detection.

Implements the four hooks that the SageMaker PyTorch Serving container
invokes for real-time inference:

    model_fn   → load model weights
    input_fn   → decode incoming image bytes to numpy
    predict_fn → run detection
    output_fn  → serialise result to JSON

Supported content types:
    Input  : image/jpeg, image/png
    Output : application/json
"""

import io
import json
import logging
import os

import numpy as np
from PIL import Image

from sagemaker_yolo.model_loader import load_model
from sagemaker_yolo.predict import run_inference

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SageMaker hooks
# ---------------------------------------------------------------------------


def model_fn(model_dir: str):
    """
    Load the YOLO model from *model_dir*.

    SageMaker copies model artefacts into ``model_dir`` at deploy time.

    Args:
        model_dir: Directory containing model weights.

    Returns:
        Loaded YOLO model (real or mock).
    """
    # ---- Fix 1: construct full path to the weights file -------------------
    model_path = os.path.join(model_dir, "yolov8_flood_highacc.pt")
    logger.info("model_fn: loading model from %s", model_path)
    return load_model(model_path)


def input_fn(request_body: bytes, content_type: str) -> np.ndarray:
    """
    Decode raw image bytes into a BGR numpy array.

    Args:
        request_body: Raw bytes of the incoming image.
        content_type: MIME type (``image/jpeg`` or ``image/png``).

    Returns:
        BGR numpy array (H×W×3, ``uint8``).

    Raises:
        ValueError: If *content_type* is unsupported.
    """
    supported = {"image/jpeg", "image/png"}
    if content_type not in supported:
        raise ValueError(
            f"Unsupported content type '{content_type}'. "
            f"Must be one of {supported}."
        )

    logger.info("input_fn: decoding %s (%d bytes)", content_type, len(request_body))

    # PIL → numpy (RGB) → BGR for OpenCV compatibility
    pil_image = Image.open(io.BytesIO(request_body)).convert("RGB")
    rgb_array = np.array(pil_image, dtype=np.uint8)
    bgr_array = rgb_array[:, :, ::-1].copy()  # RGB → BGR

    logger.info("input_fn: decoded image shape %s", bgr_array.shape)
    return bgr_array


def predict_fn(input_data: np.ndarray, model) -> dict:
    """
    Run YOLO detection on the decoded image.

    Args:
        input_data: BGR numpy array from ``input_fn``.
        model: Model object from ``model_fn``.

    Returns:
        Detection dict matching FloodWatch schema.
    """
    logger.info("predict_fn: running inference on shape %s", input_data.shape)
    return run_inference(model, input_data)


def output_fn(prediction: dict, accept: str) -> str:
    """
    Serialise the prediction dict to JSON.

    Args:
        prediction: Detection dict from ``predict_fn``.
        accept: Requested response MIME type.

    Returns:
        JSON string of the prediction.

    Raises:
        ValueError: If *accept* is not ``application/json``.
    """
    if accept != "application/json":
        raise ValueError(
            f"Unsupported accept type '{accept}'. "
            f"Must be 'application/json'."
        )

    logger.info(
        "output_fn: serialising %d detection(s)",
        prediction.get("detections_count", 0),
    )
    return json.dumps(prediction, indent=2)
