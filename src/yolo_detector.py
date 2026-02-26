"""
yolo_detector.py — YOLOv8 object detection and water depth estimation.

Detects reference objects (car, person, bicycle, truck, bus) in flood images
and estimates water depth based on detected object height and an assumed
waterline ratio.
"""

import logging

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

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

# Default fraction of the object assumed to be submerged
DEFAULT_WATERLINE_RATIO = 0.25


def estimate_depth(
    frame: np.ndarray,
    model_path: str = "yolov8n.pt",
    waterline_ratio: float = DEFAULT_WATERLINE_RATIO,
    confidence_threshold: float = 0.3,
) -> dict:
    """
    Run YOLOv8 detection and estimate water depth from reference objects.

    Args:
        frame: BGR numpy array of the flood scene.
        model_path: Path to YOLOv8 weights file.
        waterline_ratio: Assumed fraction of the reference object submerged
                         in water (0.0 to 1.0).
        confidence_threshold: Minimum detection confidence to consider.

    Returns:
        Dict with keys:
            - water_depth_cm (float | None): Estimated depth in cm.
            - reference_object (str | None): Object used for estimation.
            - confidence (float | None): Detection confidence score.
    """
    fallback = {
        "water_depth_cm": None,
        "reference_object": None,
        "confidence": None,
    }

    try:
        model = YOLO(model_path)
        results = model(frame, verbose=False)
    except Exception as e:
        logger.error(f"YOLOv8 inference failed: {e}")
        return fallback

    if not results or len(results) == 0:
        logger.info("No YOLO results returned.")
        return fallback

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
                # Get bounding box height in pixels
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                box_height_px = y2 - y1

                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": REFERENCE_CLASS_IDS[cls_id],
                        "confidence": conf,
                        "box_height_px": box_height_px,
                    }
                )

    if not detections:
        logger.info("No reference objects detected in frame.")
        return fallback

    # Pick the detection with highest confidence
    best = max(detections, key=lambda d: d["confidence"])

    # Estimate water depth
    real_height = REFERENCE_HEIGHTS_CM[best["class_name"]]
    water_depth_cm = round(real_height * waterline_ratio, 1)

    logger.info(
        f"Depth estimate: {water_depth_cm} cm using {best['class_name']} "
        f"(conf: {best['confidence']:.2f})"
    )

    return {
        "water_depth_cm": water_depth_cm,
        "reference_object": best["class_name"],
        "confidence": round(best["confidence"], 4),
    }
