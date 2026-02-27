"""
train_flood_yolo_highacc.py — High-accuracy YOLOv8 flood model training.

Trains a YOLOv8s/m model on the expanded, quality-audited flood dataset
with higher resolution, extended epochs, and aggressive augmentations.

Usage:
    python train_flood_yolo_highacc.py
    python train_flood_yolo_highacc.py --model yolov8m.pt --imgsz 832
    python train_flood_yolo_highacc.py --epochs 150 --batch 8

Baseline: YOLOv8n, 640px, 40 epochs → mAP50 ≈ 0.69
Target:   YOLOv8s, 768px, 100 epochs → mAP50 ≥ 0.80
"""

import argparse
import logging
import os
import shutil
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_YAML = os.path.join(PROJECT_ROOT, "data", "flood_dataset.yaml")
OUTPUT_MODEL = os.path.join(PROJECT_ROOT, "models", "yolov8_flood_highacc.pt")

# Baseline metrics for comparison
BASELINE_METRICS = {
    "model": "yolov8n",
    "imgsz": 640,
    "epochs": 40,
    "mAP50": 0.69,
}


def train(args):
    """Run the high-accuracy training pipeline."""

    # ── Pre-flight checks ──
    if not os.path.isfile(DATA_YAML):
        logger.error(f"Dataset config not found: {DATA_YAML}")
        logger.error("Run: python scripts/download_additional_floods.py first")
        sys.exit(1)

    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_mem / 1e9
            logger.info(f"GPU: {gpu_name} ({gpu_mem:.1f} GB)")
        else:
            logger.warning("No CUDA GPU detected. Training will be very slow.")
    except ImportError:
        logger.warning("PyTorch not found. YOLO will handle device selection.")
        gpu_available = False

    # ── YOLO Training ──
    from ultralytics import YOLO

    logger.info(f"Loading model: {args.model}")
    model = YOLO(args.model)

    train_name = args.name or "yolov8_flood_highacc"

    logger.info("=" * 60)
    logger.info("  FloodWatch High-Accuracy YOLO Training")
    logger.info("=" * 60)
    logger.info(f"  Model:      {args.model}")
    logger.info(f"  Image size: {args.imgsz}")
    logger.info(f"  Epochs:     {args.epochs}")
    logger.info(f"  Batch:      {args.batch}")
    logger.info(f"  Patience:   {args.patience}")
    logger.info(f"  Data:       {DATA_YAML}")
    logger.info(f"  Run name:   {train_name}")
    logger.info("=" * 60)

    # Train with enhanced configuration
    results = model.train(
        data=DATA_YAML,
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch if args.batch != "auto" else -1,
        patience=args.patience,
        device=0 if gpu_available else "cpu",
        name=train_name,
        pretrained=True,
        exist_ok=True,
        verbose=True,

        # ── Enhanced Augmentations ──
        mosaic=1.0,             # Mosaic augmentation
        hsv_h=0.015,            # Hue shift ±1.5%
        hsv_s=0.7,              # Saturation shift ±70%
        hsv_v=0.4,              # Value shift ±40%
        flipud=0.5,             # Vertical flip 50%
        fliplr=0.5,             # Horizontal flip 50%
        scale=0.5,              # Scale ±50%
        translate=0.1,          # Translate ±10%
        degrees=10.0,           # Rotation ±10°
        shear=2.0,              # Shear ±2°
        perspective=0.0005,     # Subtle perspective
        mixup=0.1,              # Mixup probability
        copy_paste=0.1,         # Copy-paste augmentation

        # ── Optimizer settings ──
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        weight_decay=0.0005,
        warmup_epochs=5,
        cos_lr=True,            # Cosine LR schedule

        # ── Other ──
        workers=4,
        seed=42,
        val=True,
        plots=True,
        save=True,
    )

    logger.info("\n✅ Training complete!")

    # ── Copy best weights ──
    best_pt = os.path.join("runs", "detect", train_name, "weights", "best.pt")
    if os.path.isfile(best_pt):
        os.makedirs(os.path.dirname(OUTPUT_MODEL), exist_ok=True)
        shutil.copy2(best_pt, OUTPUT_MODEL)
        model_size = os.path.getsize(OUTPUT_MODEL) / 1024 / 1024
        logger.info(f"Best weights copied to: {OUTPUT_MODEL} ({model_size:.1f} MB)")
    else:
        logger.warning(f"Best weights not found at {best_pt}")

    # ── Evaluate and compare ──
    print()
    print("=" * 60)
    print("  Training Results — Comparison with Baseline")
    print("=" * 60)

    try:
        best_model = YOLO(best_pt if os.path.isfile(best_pt) else OUTPUT_MODEL)
        metrics = best_model.val(data=DATA_YAML)

        new_map50 = metrics.box.map50
        new_map = metrics.box.map
        new_precision = metrics.box.mp
        new_recall = metrics.box.mr

        print(f"\n  {'Metric':<20} {'Baseline':<15} {'New Model':<15} {'Change':<10}")
        print(f"  {'─' * 60}")
        print(f"  {'Model':<20} {BASELINE_METRICS['model']:<15} {args.model:<15}")
        print(f"  {'Image Size':<20} {BASELINE_METRICS['imgsz']:<15} {args.imgsz:<15}")
        print(f"  {'Epochs':<20} {BASELINE_METRICS['epochs']:<15} {args.epochs:<15}")
        print(f"  {'─' * 60}")
        print(f"  {'Precision':<20} {'N/A':<15} {new_precision:.4f}")
        print(f"  {'Recall':<20} {'N/A':<15} {new_recall:.4f}")

        delta_50 = new_map50 - BASELINE_METRICS["mAP50"]
        sign = "+" if delta_50 >= 0 else ""
        print(f"  {'mAP50':<20} {BASELINE_METRICS['mAP50']:<15.4f} {new_map50:<15.4f} {sign}{delta_50:.4f}")
        print(f"  {'mAP50-95':<20} {'N/A':<15} {new_map:.4f}")

        if new_map50 >= 0.80:
            print(f"\n  🎯 Target mAP50 ≥ 0.80 ACHIEVED! ({new_map50:.4f})")
        else:
            print(f"\n  ⚠️  mAP50 = {new_map50:.4f} — target 0.80 not yet reached")
            print(f"      Consider: more data, yolov8m.pt, or longer training")

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Train high-accuracy FloodWatch YOLO model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python train_flood_yolo_highacc.py
    python train_flood_yolo_highacc.py --model yolov8m.pt --imgsz 832
    python train_flood_yolo_highacc.py --epochs 150 --patience 30
        """,
    )
    parser.add_argument(
        "--model", default="yolov8s.pt",
        choices=["yolov8s.pt", "yolov8m.pt", "yolov8l.pt"],
        help="YOLO model checkpoint (default: yolov8s.pt)",
    )
    parser.add_argument(
        "--imgsz", type=int, default=768,
        choices=[640, 768, 832, 1024],
        help="Training image size (default: 768)",
    )
    parser.add_argument(
        "--epochs", type=int, default=100,
        help="Maximum training epochs (default: 100)",
    )
    parser.add_argument(
        "--batch", default="auto",
        help="Batch size: integer or 'auto' (default: auto)",
    )
    parser.add_argument(
        "--patience", type=int, default=20,
        help="Early stopping patience (default: 20)",
    )
    parser.add_argument(
        "--name", default=None,
        help="Run name (default: yolov8_flood_highacc)",
    )
    args = parser.parse_args()

    # Parse batch (can be int or "auto")
    if args.batch != "auto":
        try:
            args.batch = int(args.batch)
        except ValueError:
            logger.error(f"Invalid batch value: {args.batch}")
            sys.exit(1)

    train(args)


if __name__ == "__main__":
    main()
