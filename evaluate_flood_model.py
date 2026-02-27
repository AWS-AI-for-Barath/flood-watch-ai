"""
evaluate_flood_model.py — Compare flood-tuned vs COCO YOLO models.

Usage:
    python evaluate_flood_model.py                            # all local images
    python evaluate_flood_model.py weather_houseflood2.jpg    # specific image

Saves annotated predictions to outputs/flood_predictions/
"""

import argparse
import glob
import logging
import os

import cv2
from ultralytics import YOLO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
HIGHACC_MODEL = os.path.join(PROJECT_ROOT, "models", "yolov8_flood_highacc.pt")
FLOOD_MODEL = os.path.join(PROJECT_ROOT, "models", "yolov8_flood.pt")
COCO_MODEL = "yolov8s.pt"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs", "flood_predictions")


def evaluate_model(model_path: str, image_path: str, label: str, conf: float = 0.4):
    """Run inference and return annotated image + detection count."""
    model = YOLO(model_path)
    results = model(image_path, verbose=False, conf=conf)

    count = 0
    for r in results:
        if r.boxes is not None:
            count += len(r.boxes)

    # Get annotated image
    annotated = results[0].plot() if results else None
    return annotated, count


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate flood-tuned YOLO models vs COCO baseline"
    )
    parser.add_argument(
        "images", nargs="*",
        help="Image paths to evaluate (default: all local images)",
    )
    parser.add_argument(
        "--conf", type=float, default=0.4,
        help="Confidence threshold (default: 0.4)",
    )
    args = parser.parse_args()

    # Find images
    if args.images:
        images = args.images
    else:
        images = []
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            images.extend(glob.glob(os.path.join(PROJECT_ROOT, ext)))
        if not images:
            logger.error("No images found. Provide image paths as arguments.")
            return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Detect available models
    has_highacc = os.path.isfile(HIGHACC_MODEL)
    has_flood = os.path.isfile(FLOOD_MODEL)

    if not has_highacc and not has_flood:
        logger.warning(
            f"No flood models found. Only running COCO model evaluation.\n"
            f"  Expected: {HIGHACC_MODEL}\n"
            f"  Or:       {FLOOD_MODEL}"
        )

    print()
    print("=" * 70)
    print("  FloodWatch YOLO Model Evaluation")
    print("=" * 70)
    print(f"  Confidence threshold: {args.conf}")
    print(f"  Models available:")
    print(f"    COCO (yolov8s):     ✅")
    print(f"    Flood baseline:     {'✅' if has_flood else '❌'}")
    print(f"    Flood high-acc:     {'✅' if has_highacc else '❌'}")

    for img_path in images:
        basename = os.path.basename(img_path)
        name = os.path.splitext(basename)[0]
        print(f"\n  Image: {basename}")
        print(f"  {'─' * 50}")

        # COCO model
        coco_annotated, coco_count = evaluate_model(
            COCO_MODEL, img_path, "COCO", conf=args.conf
        )
        print(f"  COCO model (yolov8s): {coco_count} detections")

        if coco_annotated is not None:
            out_path = os.path.join(OUTPUT_DIR, f"{name}_coco.jpg")
            cv2.imwrite(out_path, coco_annotated)

        # Flood baseline model
        if has_flood:
            flood_annotated, flood_count = evaluate_model(
                FLOOD_MODEL, img_path, "Flood", conf=args.conf
            )
            print(f"  Flood baseline:       {flood_count} detections")

            if flood_annotated is not None:
                out_path = os.path.join(OUTPUT_DIR, f"{name}_flood.jpg")
                cv2.imwrite(out_path, flood_annotated)

        # High-accuracy model
        if has_highacc:
            highacc_annotated, highacc_count = evaluate_model(
                HIGHACC_MODEL, img_path, "HighAcc", conf=args.conf
            )
            print(f"  Flood high-accuracy:  {highacc_count} detections")

            if highacc_annotated is not None:
                out_path = os.path.join(OUTPUT_DIR, f"{name}_highacc.jpg")
                cv2.imwrite(out_path, highacc_annotated)

            # Best comparison
            best_label = "high-accuracy"
            best_count = highacc_count
            if has_flood and flood_count > highacc_count:
                best_label = "baseline flood"
                best_count = flood_count
            if coco_count > best_count:
                best_label = "COCO"
            print(f"  → Best: {best_label} model")

    print(f"\n  Predictions saved to: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
