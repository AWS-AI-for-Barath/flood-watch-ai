"""
yolo_detector.py — YOLOv8 object detection and submergence estimation.

Detects reference objects (car, person, bicycle, truck, bus) in flood images
and estimates submergence ratio based on bounding box vertical position
relative to the image frame.

Model fallback chain:
  1. yolov8_flood_highacc.pt  (high-accuracy flood-tuned)
  2. yolov8_flood.pt          (baseline flood-tuned)
  3. yolov8s.pt               (COCO-pretrained)
"""

import logging
import os

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# High-accuracy flood-tuned model (preferred)
FLOOD_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "yolov8_flood_highacc.pt"
)

# Baseline flood-tuned model (fallback)
FLOOD_MODEL_FALLBACK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "yolov8_flood.pt"
)

# COCO-pretrained model (last resort)
COCO_MODEL_PATH = "yolov8s.pt"

# Real-world reference heights in centimeters
REFERENCE_HEIGHTS_CM = {
    "car": 150,
    "person": 170,
    "bicycle": 100,
    "truck": 250,
    "bus": 300,
}

# COCO class IDs for reference objects
REFERENCE_CLASS_IDS = {
    2: "car",
    0: "person",
    1: "bicycle",
    7: "truck",
    5: "bus",
}

# Default submergence ratio (fraction of object underwater)
DEFAULT_SUBMERGENCE_RATIO = 0.25


def _resolve_model_path(model_path: str | None = None) -> str:
    """Resolve model path with 3-tier fallback chain."""
    if model_path and os.path.isfile(model_path):
        return model_path

    # Tier 1: High-accuracy flood model
    if os.path.isfile(FLOOD_MODEL_PATH):
        logger.info(f"Using high-accuracy flood model: {FLOOD_MODEL_PATH}")
        return FLOOD_MODEL_PATH

    # Tier 2: Baseline flood model
    if os.path.isfile(FLOOD_MODEL_FALLBACK):
        logger.info(f"Using baseline flood model: {FLOOD_MODEL_FALLBACK}")
        return FLOOD_MODEL_FALLBACK

    # Tier 3: COCO-pretrained
    logger.warning(
        f"No flood model found. "
        f"Falling back to COCO-pretrained {COCO_MODEL_PATH}"
    )
    return COCO_MODEL_PATH


def _compute_submergence_ratio(
    y1: float, y2: float, img_height: int
) -> float:
    """
    Estimate submergence ratio from bounding box position.

    Uses the vertical position of the bounding box bottom relative to the
    image height as a proxy for water level. Objects whose bottom edge is
    closer to the image bottom are assumed to be more submerged.

    Args:
        y1: Top of bounding box (pixels).
        y2: Bottom of bounding box (pixels).
        img_height: Height of the image (pixels).

    Returns:
        Submergence ratio between 0.0 (dry) and 1.0 (fully submerged).
    """
    box_height = y2 - y1
    if box_height <= 0 or img_height <= 0:
        return DEFAULT_SUBMERGENCE_RATIO

    # The lower the object sits in the frame, the more submerged it likely is.
    # bottom_ratio = 1.0 means the box touches the image bottom (deepest water).
    bottom_ratio = y2 / img_height

    # Scale: object at very bottom → high submergence; top half → minimal
    submergence = round(min(1.0, max(0.0, bottom_ratio * 0.6)), 2)
    return submergence


def estimate_depth(
    frame: np.ndarray,
    model_path: str | None = None,
    submergence_ratio: float | None = None,
    confidence_threshold: float = 0.4,
) -> dict:
    """
    Run YOLOv8 detection and estimate submergence from reference objects.

    Args:
        frame: BGR numpy array of the flood scene.
        model_path: Path to YOLOv8 weights file.
        submergence_ratio: Override submergence ratio (0.0–1.0). If None,
                           computed dynamically from bounding box position.
        confidence_threshold: Minimum detection confidence to consider.

    Returns:
        Dict with keys:
            - submergence_ratio (float | None): Fraction of object submerged.
            - reference_object (str | None): Object used for estimation.
            - confidence (float | None): Detection confidence score.
    """
    fallback = {
        "submergence_ratio": None,
        "reference_object": None,
        "confidence": None,
    }

    resolved_path = _resolve_model_path(model_path)

    try:
        model = YOLO(resolved_path)
        results = model(frame, verbose=False)
    except Exception as e:
        logger.error(f"YOLOv8 inference failed: {e}")
        return fallback

    if not results or len(results) == 0:
        logger.info("No YOLO results returned.")
        return fallback

    img_height = frame.shape[0]

    # Collect all reference-object detections
    detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue

        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())
            conf = float(boxes.conf[i].item())

            if cls_id in REFERENCE_CLASS_IDS and conf >= confidence_threshold:
                # Get bounding box coordinates
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                box_height_px = y2 - y1

                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": REFERENCE_CLASS_IDS[cls_id],
                        "confidence": conf,
                        "box_height_px": box_height_px,
                        "y1": y1,
                        "y2": y2,
                    }
                )

    if not detections:
        logger.info("No reference objects detected in frame.")
        return fallback

    # Pick the detection with highest confidence
    best = max(detections, key=lambda d: d["confidence"])

    # Compute submergence ratio
    if submergence_ratio is not None:
        ratio = round(min(1.0, max(0.0, submergence_ratio)), 2)
    else:
        ratio = _compute_submergence_ratio(best["y1"], best["y2"], img_height)

    logger.info(
        f"Submergence: {ratio:.0%} of {best['class_name']} submerged "
        f"(conf: {best['confidence']:.2f})"
    )

    return {
        "submergence_ratio": ratio,
        "reference_object": best["class_name"],
        "confidence": round(best["confidence"], 4),
    }
