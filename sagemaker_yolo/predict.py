"""
predict.py — Detection wrapper for YOLO flood inference.

Runs a YOLO (or mock) model on a numpy image and returns detections in
the exact FloodWatch JSON schema expected by downstream consumers.

Schema
------
{
    "detections": [
        {"label": "car", "confidence": 0.82, "bbox": [x1, y1, x2, y2]}
    ],
    "detections_count": 1
}
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def run_inference(model, image: np.ndarray) -> dict:
    """
    Run YOLO inference on *image* and return FloodWatch-schema detections.

    Args:
        model: A YOLO model instance (real Ultralytics or MockModel).
        image: BGR numpy array (H×W×C, ``uint8``).

    Returns:
        Dict with ``detections`` list and ``detections_count``.
    """
    # ---- Fix 2: BGR → RGB conversion (OpenCV loads BGR, YOLO expects RGB) --
    if image is not None and len(image.shape) == 3 and image.shape[2] == 3:
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    else:
        image_rgb = image

    try:
        results = model(image_rgb, verbose=False)
    except TypeError:
        # MockModel may not accept `verbose` kwarg
        results = model(image_rgb)
    except Exception as exc:
        logger.error("Inference failed: %s", exc)
        return {"detections": [], "detections_count": 0}

    detections = []

    for result in results:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue

        # Resolve class-name mapping
        names = getattr(result, "names", None) or getattr(model, "names", {})

        for i in range(len(boxes.cls)):
            cls_id = int(boxes.cls[i])
            # ---- Fix 3: explicit Python-native casts for JSON safety ------
            confidence = float(boxes.conf[i])
            x1, y1, x2, y2 = [int(v) for v in boxes.xyxy[i].tolist()]

            label = names.get(cls_id, f"class_{cls_id}")

            detections.append(
                {
                    "label": label,
                    "confidence": round(confidence, 4),
                    "bbox": [x1, y1, x2, y2],
                }
            )

    logger.info("Detected %d object(s)", len(detections))
    return {
        "detections": detections,
        "detections_count": len(detections),
    }
