"""
test_local.py — Local end-to-end test for SageMaker YOLO inference.

Usage:
    python sagemaker_yolo/test_local.py

Loads the model, reads a sample flood image, runs inference, and
pretty-prints the JSON result.  No AWS credentials needed.
"""

import json
import logging
import os
import sys

import cv2

# Ensure the repo root is on sys.path so `sagemaker_yolo` is importable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from sagemaker_yolo.model_loader import load_model  # noqa: E402
from sagemaker_yolo.predict import run_inference      # noqa: E402

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

SAMPLE_IMAGE = os.path.join(REPO_ROOT, "weather_houseflood2.jpg")
MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolov8_flood_highacc.pt")

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    )
    logger = logging.getLogger("test_local")

    # 1. Load model
    logger.info("Loading model from: %s", MODEL_PATH)
    model = load_model(MODEL_PATH)
    logger.info("Model type: %s", type(model).__name__)

    # 2. Read sample image
    if not os.path.isfile(SAMPLE_IMAGE):
        logger.error("Sample image not found: %s", SAMPLE_IMAGE)
        sys.exit(1)

    image = cv2.imread(SAMPLE_IMAGE)
    if image is None:
        logger.error("Failed to read image: %s", SAMPLE_IMAGE)
        sys.exit(1)

    logger.info("Image loaded: %s  shape=%s", SAMPLE_IMAGE, image.shape)

    # 3. Run inference
    result = run_inference(model, image)

    # 4. Print JSON output
    print("\n" + "=" * 60)
    print("  FloodWatch — SageMaker YOLO Local Inference Result")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    print("=" * 60 + "\n")

    # 5. Quick sanity checks
    assert "detections" in result, "Missing 'detections' key"
    assert "detections_count" in result, "Missing 'detections_count' key"
    assert result["detections_count"] == len(result["detections"]), (
        "detections_count mismatch"
    )

    for det in result["detections"]:
        assert "label" in det, "Detection missing 'label'"
        assert "confidence" in det, "Detection missing 'confidence'"
        assert "bbox" in det, "Detection missing 'bbox'"
        assert len(det["bbox"]) == 4, "bbox must have exactly 4 values"

    logger.info("All sanity checks passed.")


if __name__ == "__main__":
    main()
