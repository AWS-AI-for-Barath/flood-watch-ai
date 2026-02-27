"""
balance_classes.py — Analyze and balance class distribution in YOLO dataset.

Detects class imbalance and applies oversampling + augmentation bias to
bring minority classes closer to the median count.

Usage:
    python scripts/balance_classes.py                      # Analyze only
    python scripts/balance_classes.py --balance             # Apply oversampling
    python scripts/balance_classes.py --balance --max-ratio 3.0
"""

import argparse
import logging
import os
import random
import shutil
from collections import Counter, defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "flood_dataset")

CLASS_NAMES = {0: "person", 1: "car", 2: "bicycle", 3: "motorcycle", 4: "bus", 5: "truck"}


def analyze_class_distribution(dataset_dir: str, split: str = "train") -> dict:
    """
    Count annotations per class in the training set.

    Returns:
        Dict mapping class_id -> count of annotations.
    """
    labels_dir = os.path.join(dataset_dir, split, "labels")
    if not os.path.isdir(labels_dir):
        logger.warning(f"Labels directory not found: {labels_dir}")
        return {}

    class_counts = Counter()
    images_per_class = defaultdict(set)

    for fname in os.listdir(labels_dir):
        if not fname.endswith(".txt"):
            continue

        filepath = os.path.join(labels_dir, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 5:
                    try:
                        cls_id = int(parts[0])
                        class_counts[cls_id] += 1
                        images_per_class[cls_id].add(fname)
                    except ValueError:
                        continue

    return {
        "annotation_counts": dict(class_counts),
        "image_counts": {k: len(v) for k, v in images_per_class.items()},
        "images_per_class": dict(images_per_class),
    }


def detect_imbalance(class_counts: dict, threshold: float = 0.5) -> dict:
    """
    Detect class imbalance.

    A class is considered underrepresented if its count is less than
    threshold * median_count.

    Returns:
        Dict with majority/minority classifications and balance ratios.
    """
    if not class_counts:
        return {"imbalanced": False, "details": {}}

    counts = sorted(class_counts.values())
    median = counts[len(counts) // 2]

    details = {}
    for cls_id, count in class_counts.items():
        ratio = count / median if median > 0 else 0
        status = "minority" if ratio < threshold else ("majority" if ratio > 2.0 else "balanced")
        details[cls_id] = {
            "count": count,
            "ratio_to_median": round(ratio, 2),
            "status": status,
            "name": CLASS_NAMES.get(cls_id, f"class_{cls_id}"),
        }

    is_imbalanced = any(d["status"] == "minority" for d in details.values())

    return {"imbalanced": is_imbalanced, "median": median, "details": details}


def oversample_minority(
    dataset_dir: str,
    images_per_class: dict,
    imbalance_details: dict,
    max_ratio: float = 3.0,
    split: str = "train",
) -> int:
    """
    Oversample minority classes by duplicating images with augmented names.

    Creates copies of images/labels containing minority class annotations
    to bring their count closer to the median.

    Returns:
        Number of images duplicated.
    """
    images_dir = os.path.join(dataset_dir, split, "images")
    labels_dir = os.path.join(dataset_dir, split, "labels")

    duplicated = 0
    median = imbalance_details.get("median", 0)

    for cls_id, info in imbalance_details.get("details", {}).items():
        if info["status"] != "minority":
            continue

        cls_images = list(images_per_class.get(cls_id, set()))
        if not cls_images:
            continue

        target_count = min(int(median * max_ratio), median)
        current_count = info["count"]
        needed = max(0, target_count - current_count)

        if needed == 0:
            continue

        logger.info(
            f"Oversampling class {cls_id} ({info['name']}): "
            f"{current_count} → ~{target_count} annotations"
        )

        # Duplicate images containing this class
        copies_needed = max(1, needed // max(1, len(cls_images)))
        for label_fname in cls_images:
            for copy_idx in range(int(copies_needed)):
                base_name = os.path.splitext(label_fname)[0]
                new_label_name = f"{base_name}_dup{copy_idx}.txt"
                new_label_path = os.path.join(labels_dir, new_label_name)

                if os.path.exists(new_label_path):
                    continue

                # Copy label
                src_label = os.path.join(labels_dir, label_fname)
                if os.path.isfile(src_label):
                    shutil.copy2(src_label, new_label_path)

                # Find and copy image
                for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                    img_fname = base_name + ext
                    src_img = os.path.join(images_dir, img_fname)
                    if os.path.isfile(src_img):
                        new_img_name = f"{base_name}_dup{copy_idx}{ext}"
                        shutil.copy2(src_img, os.path.join(images_dir, new_img_name))
                        duplicated += 1
                        break

                if duplicated >= needed:
                    break
            if duplicated >= needed:
                break

    return duplicated


def create_flipped_copies(
    dataset_dir: str,
    images_per_class: dict,
    imbalance_details: dict,
    split: str = "train",
) -> int:
    """
    Create horizontally-flipped copies of minority-class images.

    For YOLO format: x_center = 1.0 - x_center (horizontal flip).

    Returns:
        Number of augmented images created.
    """
    images_dir = os.path.join(dataset_dir, split, "images")
    labels_dir = os.path.join(dataset_dir, split, "labels")
    created = 0

    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("Pillow not installed; skipping flip augmentation")
        return 0

    for cls_id, info in imbalance_details.get("details", {}).items():
        if info["status"] != "minority":
            continue

        cls_images = list(images_per_class.get(cls_id, set()))

        for label_fname in cls_images:
            base_name = os.path.splitext(label_fname)[0]
            flip_label_name = f"{base_name}_flip.txt"
            flip_label_path = os.path.join(labels_dir, flip_label_name)

            if os.path.exists(flip_label_path):
                continue

            # Flip label coordinates
            src_label = os.path.join(labels_dir, label_fname)
            if not os.path.isfile(src_label):
                continue

            flipped_lines = []
            with open(src_label, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        parts[1] = str(round(1.0 - float(parts[1]), 6))  # Flip x_center
                        flipped_lines.append(" ".join(parts))

            if not flipped_lines:
                continue

            with open(flip_label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(flipped_lines) + "\n")

            # Flip image
            for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                img_fname = base_name + ext
                src_img = os.path.join(images_dir, img_fname)
                if os.path.isfile(src_img):
                    flip_img_name = f"{base_name}_flip{ext}"
                    try:
                        img = Image.open(src_img)
                        flipped = ImageOps.mirror(img)
                        flipped.save(os.path.join(images_dir, flip_img_name))
                        created += 1
                    except Exception as e:
                        logger.warning(f"Failed to flip {img_fname}: {e}")
                    break

    return created


def print_distribution_table(class_counts: dict, title: str = "Class Distribution"):
    """Print a formatted table of class distribution."""
    print(f"\n  {title}")
    print(f"  {'─' * 45}")
    print(f"  {'Class ID':<10} {'Name':<15} {'Count':<10}")
    print(f"  {'─' * 45}")

    for cls_id in sorted(class_counts.keys()):
        name = CLASS_NAMES.get(cls_id, f"class_{cls_id}")
        count = class_counts[cls_id]
        print(f"  {cls_id:<10} {name:<15} {count:<10}")

    total = sum(class_counts.values())
    print(f"  {'─' * 45}")
    print(f"  {'Total':<10} {'':<15} {total:<10}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and balance class distribution"
    )
    parser.add_argument(
        "--dataset", default=DATASET_DIR,
        help=f"Dataset root directory (default: {DATASET_DIR})",
    )
    parser.add_argument(
        "--balance", action="store_true",
        help="Apply oversampling to balance classes",
    )
    parser.add_argument(
        "--max-ratio", type=float, default=3.0,
        help="Maximum oversampling ratio relative to median (default: 3.0)",
    )
    parser.add_argument(
        "--analyze-only", action="store_true",
        help="Only analyze distribution (no modifications)",
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  FloodWatch Class Distribution Analysis")
    print("=" * 60)

    # Analyze current distribution
    analysis = analyze_class_distribution(args.dataset)

    if not analysis.get("annotation_counts"):
        print("\n  ⚠️  No annotations found in training set")
        print("=" * 60)
        return

    print_distribution_table(analysis["annotation_counts"], "Before Balancing")

    # Check for imbalance
    imbalance = detect_imbalance(analysis["annotation_counts"])

    if imbalance["imbalanced"]:
        print(f"\n  ⚠️  Class imbalance detected!")
        for cls_id, info in imbalance["details"].items():
            if info["status"] == "minority":
                print(f"    Minority: {info['name']} (ratio: {info['ratio_to_median']}x)")
    else:
        print(f"\n  ✅ Class distribution is balanced")

    # Apply balancing if requested
    if args.balance and not args.analyze_only and imbalance["imbalanced"]:
        print(f"\n  Applying oversampling...")

        dup_count = oversample_minority(
            args.dataset,
            analysis["images_per_class"],
            imbalance,
            max_ratio=args.max_ratio,
        )
        print(f"    Duplicated images: {dup_count}")

        flip_count = create_flipped_copies(
            args.dataset,
            analysis["images_per_class"],
            imbalance,
        )
        print(f"    Flipped images: {flip_count}")

        # Re-analyze after balancing
        after = analyze_class_distribution(args.dataset)
        print_distribution_table(after["annotation_counts"], "After Balancing")
    elif not args.balance and imbalance["imbalanced"]:
        print(f"\n  Run with --balance to apply oversampling")

    print("=" * 60)


if __name__ == "__main__":
    main()
