"""
train_flood_maxacc.py — Maximum-accuracy YOLOv8m flood detection training.

Pushes detection performance toward dataset ceiling (~0.85 mAP50) using:
- YOLOv8m backbone (25.9M params)
- 832px resolution for fine-grained flood boundary detection
- 200 epochs with patience=40 early stopping
- AdamW optimizer with cosine LR schedule
- Aggressive augmentations (mosaic, mixup, HSV, scale, perspective, flips)
- Enhanced localization loss (box=7.5, CIoU)

Usage:
    python train_flood_maxacc.py
    python train_flood_maxacc.py --model yolov8l.pt --imgsz 960
    python train_flood_maxacc.py --batch 8 --device 0
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
DATASET_YAML = os.path.join(PROJECT_ROOT, "data", "flood_dataset.yaml")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "runs")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")

# ── Previous best metrics for comparison ──
BASELINE_METRICS = {
    "model": "YOLOv8s",
    "imgsz": 768,
    "epochs_trained": 100,
    "mAP50": 0.69,
    "mAP50_95": None,
    "precision": None,
    "recall": None,
}


def normalize_labels(dataset_dir: str) -> dict:
    """Convert any remaining polygon annotations to YOLO bbox format."""
    poly_count = 0
    bbox_count = 0

    for split in ("train", "val", "valid", "test"):
        lbl_dir = os.path.join(dataset_dir, split, "labels")
        if not os.path.isdir(lbl_dir):
            continue

        for fname in sorted(os.listdir(lbl_dir)):
            if not fname.endswith(".txt"):
                continue
            fpath = os.path.join(lbl_dir, fname)
            with open(fpath, "r") as f:
                lines = f.readlines()

            converted = []
            had_polygon = False
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 5:
                    converted.append(line.strip())
                    bbox_count += 1
                elif len(parts) > 5:
                    # Polygon → bbox
                    try:
                        cls_id = int(parts[0])
                        coords = [float(v) for v in parts[1:]]
                        if len(coords) % 2 == 0:
                            xs = coords[0::2]
                            ys = coords[1::2]
                            x_min = max(0, min(xs))
                            x_max = min(1, max(xs))
                            y_min = max(0, min(ys))
                            y_max = min(1, max(ys))
                            w = x_max - x_min
                            h = y_max - y_min
                            if w > 0 and h > 0:
                                xc = x_min + w / 2
                                yc = y_min + h / 2
                                converted.append(
                                    f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}"
                                )
                                poly_count += 1
                                had_polygon = True
                    except (ValueError, IndexError):
                        pass

            if had_polygon:
                with open(fpath, "w") as f:
                    f.write("\n".join(converted) + "\n")

    return {"polygons_converted": poly_count, "bbox_unchanged": bbox_count}


def oversample_minority_classes(dataset_dir: str, target_ratio: float = 0.7):
    """
    Oversample minority classes to reduce class imbalance.

    Copies images+labels of underrepresented classes so their counts
    approach target_ratio of the majority class count.
    """
    from collections import Counter
    from PIL import Image, ImageOps

    train_img_dir = os.path.join(dataset_dir, "train", "images")
    train_lbl_dir = os.path.join(dataset_dir, "train", "labels")

    if not os.path.isdir(train_lbl_dir):
        logger.warning("No train/labels directory found.")
        return

    # Count annotations per class and track which files contain each class
    class_counts = Counter()
    class_files = {}

    for fname in os.listdir(train_lbl_dir):
        if not fname.endswith(".txt"):
            continue
        with open(os.path.join(train_lbl_dir, fname)) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    cls = int(parts[0])
                    class_counts[cls] += 1
                    class_files.setdefault(cls, set()).add(fname)

    if not class_counts:
        return

    max_count = max(class_counts.values())
    target = int(max_count * target_ratio)
    dup_count = 0

    logger.info("Class distribution before oversampling:")
    for cls_id in sorted(class_counts):
        logger.info(f"  Class {cls_id}: {class_counts[cls_id]} annotations")

    for cls_id, count in class_counts.items():
        if count >= target:
            continue

        files = list(class_files.get(cls_id, []))
        if not files:
            continue

        needed = target - count
        idx = 0
        while needed > 0 and idx < needed + len(files):
            src_lbl = files[idx % len(files)]
            base = os.path.splitext(src_lbl)[0]
            dup_suffix = f"_dup{idx}"

            dst_lbl = os.path.join(train_lbl_dir, f"{base}{dup_suffix}.txt")
            if os.path.exists(dst_lbl):
                idx += 1
                continue

            # Copy label
            shutil.copy2(os.path.join(train_lbl_dir, src_lbl), dst_lbl)

            # Copy + augment image (horizontal flip for variation)
            for ext in (".jpg", ".jpeg", ".png"):
                src_img = os.path.join(train_img_dir, base + ext)
                if os.path.isfile(src_img):
                    dst_img = os.path.join(train_img_dir, f"{base}{dup_suffix}{ext}")
                    try:
                        img = Image.open(src_img)
                        flipped = ImageOps.mirror(img)
                        flipped.save(dst_img)

                        # Flip label x-coordinates
                        with open(dst_lbl) as f:
                            lines = f.readlines()
                        flipped_lines = []
                        for line in lines:
                            parts = line.strip().split()
                            if len(parts) == 5:
                                cls, xc, yc, w, h = (
                                    parts[0],
                                    float(parts[1]),
                                    parts[2],
                                    parts[3],
                                    parts[4],
                                )
                                flipped_lines.append(
                                    f"{cls} {1.0 - xc:.6f} {yc} {w} {h}"
                                )
                        with open(dst_lbl, "w") as f:
                            f.write("\n".join(flipped_lines) + "\n")
                    except Exception:
                        shutil.copy2(src_img, dst_img)
                    break

            dup_count += 1
            needed -= 1
            idx += 1

    logger.info(f"Oversampled {dup_count} images for minority classes.")


def tighten_bboxes(dataset_dir: str, shrink_factor: float = 0.03):
    """
    Tighten loose bounding boxes by shrinking margins slightly.

    Reduces each box dimension by shrink_factor (3% default) on each side,
    preserving coverage while removing excess padding from auto-annotations.
    """
    total_tightened = 0

    for split in ("train", "val", "valid", "test"):
        lbl_dir = os.path.join(dataset_dir, split, "labels")
        if not os.path.isdir(lbl_dir):
            continue

        for fname in sorted(os.listdir(lbl_dir)):
            if not fname.endswith(".txt"):
                continue
            fpath = os.path.join(lbl_dir, fname)
            with open(fpath) as f:
                lines = f.readlines()

            tightened = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) != 5:
                    tightened.append(line.strip())
                    continue
                try:
                    cls = int(parts[0])
                    xc, yc, w, h = [float(p) for p in parts[1:5]]

                    # Shrink width and height
                    new_w = w * (1 - 2 * shrink_factor)
                    new_h = h * (1 - 2 * shrink_factor)

                    # Maintain minimum size
                    new_w = max(new_w, 0.01)
                    new_h = max(new_h, 0.01)

                    # Clamp to valid range
                    xc = max(new_w / 2, min(1 - new_w / 2, xc))
                    yc = max(new_h / 2, min(1 - new_h / 2, yc))

                    tightened.append(
                        f"{cls} {xc:.6f} {yc:.6f} {new_w:.6f} {new_h:.6f}"
                    )
                    total_tightened += 1
                except (ValueError, IndexError):
                    tightened.append(line.strip())

            with open(fpath, "w") as f:
                f.write("\n".join(tightened) + "\n")

    logger.info(f"Tightened {total_tightened} bounding boxes (shrink={shrink_factor})")


def train(args):
    """Run YOLOv8m training with maximum-accuracy config."""
    import torch
    from ultralytics import YOLO

    # ── 0. Environment info ──
    gpu_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if gpu_available else "CPU"
    logger.info(f"Device: {device_name}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Resolution: {args.imgsz}px")
    logger.info(f"Epochs: {args.epochs} (patience: {args.patience})")

    # ── 1. Resolve dataset path ──
    dataset_yaml = args.data
    if not os.path.isfile(dataset_yaml):
        logger.error(f"Dataset YAML not found: {dataset_yaml}")
        sys.exit(1)

    # Read dataset dir from YAML
    import yaml
    with open(dataset_yaml) as f:
        ds_config = yaml.safe_load(f)
    dataset_dir = ds_config.get("path", "")
    if not os.path.isabs(dataset_dir):
        dataset_dir = os.path.join(PROJECT_ROOT, dataset_dir)

    # ── 2. Normalize labels (polygon → bbox safety check) ──
    logger.info("Checking label format...")
    norm_report = normalize_labels(dataset_dir)
    logger.info(
        f"Labels: {norm_report['bbox_unchanged']} bbox, "
        f"{norm_report['polygons_converted']} polygons converted"
    )

    # ── 3. Tighten bounding boxes ──
    if not args.skip_tighten:
        logger.info("Tightening loose bounding boxes...")
        tighten_bboxes(dataset_dir, shrink_factor=args.shrink)

    # ── 4. Oversample minority classes ──
    if not args.skip_balance:
        logger.info("Balancing class distribution...")
        oversample_minority_classes(dataset_dir, target_ratio=0.7)

    # ── 5. Load model ──
    model = YOLO(args.model)

    # ── 6. Train with maximum-accuracy config ──
    logger.info("\n" + "=" * 60)
    logger.info("  Starting YOLOv8m Max-Accuracy Training")
    logger.info("=" * 60)

    results = model.train(
        data=dataset_yaml,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        device=0 if gpu_available else "cpu",
        project=OUTPUT_DIR,
        name="flood_maxacc",
        exist_ok=True,
        pretrained=True,
        # ── Optimizer ──
        optimizer="AdamW",
        lr0=args.lr,
        lrf=0.01,         # Final LR = lr0 * 0.01
        weight_decay=0.0005,
        warmup_epochs=5,
        warmup_momentum=0.8,
        cos_lr=True,
        # ── Augmentations ──
        mosaic=1.0,
        mixup=0.1,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        scale=0.5,
        translate=0.1,
        perspective=0.0005,
        flipud=0.2,
        fliplr=0.5,
        degrees=5.0,
        shear=2.0,
        copy_paste=0.1,
        erasing=0.1,
        # ── Loss weights (localization emphasis) ──
        box=7.5,
        cls=0.5,
        dfl=1.5,
        # ── Other ──
        save=True,
        save_period=25,
        plots=True,
        val=True,
        verbose=True,
    )

    # ── 7. Extract metrics ──
    metrics = results.results_dict if hasattr(results, "results_dict") else {}

    precision = metrics.get("metrics/precision(B)", None)
    recall = metrics.get("metrics/recall(B)", None)
    map50 = metrics.get("metrics/mAP50(B)", None)
    map50_95 = metrics.get("metrics/mAP50-95(B)", None)

    logger.info("\n" + "=" * 60)
    logger.info("  Training Complete — Results")
    logger.info("=" * 60)
    logger.info(f"  Precision:   {precision}")
    logger.info(f"  Recall:      {recall}")
    logger.info(f"  mAP50:       {map50}")
    logger.info(f"  mAP50-95:    {map50_95}")

    # ── 8. Compare with baseline ──
    logger.info("\n  Comparison with previous best:")
    logger.info(f"  {'Metric':15s} {'Baseline':>10s} {'MaxAcc':>10s} {'Delta':>10s}")
    logger.info(f"  {'─' * 50}")
    if map50 is not None:
        baseline_map = BASELINE_METRICS["mAP50"]
        delta = map50 - baseline_map
        marker = "✅" if delta > 0 else "❌"
        logger.info(
            f"  {'mAP50':15s} {baseline_map:>10.4f} {map50:>10.4f} {delta:>+10.4f} {marker}"
        )
    if map50_95 is not None and BASELINE_METRICS["mAP50_95"] is not None:
        delta95 = map50_95 - BASELINE_METRICS["mAP50_95"]
        logger.info(
            f"  {'mAP50-95':15s} {BASELINE_METRICS['mAP50_95']:>10.4f} "
            f"{map50_95:>10.4f} {delta95:>+10.4f}"
        )

    # ── 9. Export best weights ──
    best_pt = os.path.join(OUTPUT_DIR, "flood_maxacc", "weights", "best.pt")
    if os.path.isfile(best_pt):
        os.makedirs(MODELS_DIR, exist_ok=True)
        dst = os.path.join(MODELS_DIR, "yolov8_flood_highacc.pt")
        shutil.copy2(best_pt, dst)
        logger.info(f"\n  Best model exported to: {dst}")
    else:
        logger.warning(f"  best.pt not found at {best_pt}")

    logger.info("=" * 60)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="FloodWatch YOLOv8m Maximum-Accuracy Training"
    )
    parser.add_argument(
        "--model", default="yolov8m.pt",
        help="YOLO model to train (default: yolov8m.pt)",
    )
    parser.add_argument(
        "--data", default=DATASET_YAML,
        help="Dataset YAML path",
    )
    parser.add_argument(
        "--imgsz", type=int, default=832,
        help="Training image size (default: 832)",
    )
    parser.add_argument(
        "--epochs", type=int, default=200,
        help="Number of training epochs (default: 200)",
    )
    parser.add_argument(
        "--patience", type=int, default=40,
        help="Early stopping patience (default: 40)",
    )
    parser.add_argument(
        "--batch", type=int, default=-1,
        help="Batch size (-1 = auto-fit GPU, default: -1)",
    )
    parser.add_argument(
        "--lr", type=float, default=0.002,
        help="Initial learning rate (default: 0.002)",
    )
    parser.add_argument(
        "--shrink", type=float, default=0.03,
        help="BBox tightening shrink factor (default: 0.03)",
    )
    parser.add_argument(
        "--skip-tighten", action="store_true",
        help="Skip bounding box tightening",
    )
    parser.add_argument(
        "--skip-balance", action="store_true",
        help="Skip class balancing / oversampling",
    )
    args = parser.parse_args()

    train(args)


if __name__ == "__main__":
    main()
