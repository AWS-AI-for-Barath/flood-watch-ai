"""
download_additional_floods.py — Expand FloodWatch training dataset.

Downloads additional flood imagery from Roboflow Universe public datasets
and merges them into the unified YOLO training directory.

Usage:
    python scripts/download_additional_floods.py
    python scripts/download_additional_floods.py --api-key YOUR_KEY
    python scripts/download_additional_floods.py --extra-dir path/to/manual/images
"""

import argparse
import glob
import logging
import os
import shutil
import sys
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "flood_dataset")

# Map of additional Roboflow datasets to pull.
# Format: (workspace, project_name, version, description)
ADDITIONAL_DATASETS = [
    ("modellabel", "yolo-floods-relief", 1, "Flood person detection (primary)"),
    # Add more public flood datasets here as needed:
    # ("workspace", "project-name", version, "description"),
]

# Target class mapping (matches flood_dataset.yaml)
CLASS_NAMES = {0: "person", 1: "car", 2: "bicycle", 3: "motorcycle", 4: "bus", 5: "truck"}


def count_images(directory: str) -> int:
    """Count image files in a directory."""
    count = 0
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
        count += len(glob.glob(os.path.join(directory, ext)))
    return count


def download_roboflow_datasets(api_key: str, download_dir: str) -> list[dict]:
    """Download datasets from Roboflow Universe."""
    try:
        from roboflow import Roboflow
    except ImportError:
        logger.error("roboflow package not installed. Run: pip install roboflow")
        return []

    results = []
    rf = Roboflow(api_key=api_key)

    for workspace, project_name, version_num, description in ADDITIONAL_DATASETS:
        logger.info(f"Downloading: {description} ({workspace}/{project_name} v{version_num})")
        try:
            project = rf.workspace(workspace).project(project_name)
            version = project.version(version_num)
            dest = os.path.join(download_dir, f"{project_name}_v{version_num}")
            dataset = version.download("yolov8", location=dest)
            results.append({
                "name": description,
                "path": dest,
                "status": "success",
            })
            logger.info(f"  ✅ Downloaded to {dest}")
        except Exception as e:
            logger.warning(f"  ❌ Failed to download {project_name}: {e}")
            results.append({
                "name": description,
                "path": None,
                "status": f"failed: {e}",
            })

    return results


def merge_dataset(source_dir: str, target_dir: str, split: str = "train") -> int:
    """
    Merge images and labels from a source split into the target dataset.

    Args:
        source_dir: Root of the source dataset (containing train/, valid/, test/).
        target_dir: Root of the target dataset (data/flood_dataset/).
        split: Which split to merge ('train', 'valid', 'test').

    Returns:
        Number of images merged.
    """
    # Try different naming conventions
    source_splits = {
        "train": ["train"],
        "valid": ["valid", "val"],
        "test": ["test"],
    }

    src_images = None
    src_labels = None

    for split_name in source_splits.get(split, [split]):
        img_dir = os.path.join(source_dir, split_name, "images")
        lbl_dir = os.path.join(source_dir, split_name, "labels")
        if os.path.isdir(img_dir):
            src_images = img_dir
            src_labels = lbl_dir if os.path.isdir(lbl_dir) else None
            break

    if not src_images:
        return 0

    # Target directories
    target_split = "train" if split in ("train",) else ("val" if split in ("valid", "val") else split)
    tgt_images = os.path.join(target_dir, target_split, "images")
    tgt_labels = os.path.join(target_dir, target_split, "labels")
    os.makedirs(tgt_images, exist_ok=True)
    os.makedirs(tgt_labels, exist_ok=True)

    merged = 0
    for img_file in os.listdir(src_images):
        img_ext = os.path.splitext(img_file)[1].lower()
        if img_ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            continue

        src_img = os.path.join(src_images, img_file)
        tgt_img = os.path.join(tgt_images, img_file)

        # Skip if already exists
        if os.path.exists(tgt_img):
            continue

        # Copy image
        shutil.copy2(src_img, tgt_img)

        # Copy label if exists
        label_name = os.path.splitext(img_file)[0] + ".txt"
        if src_labels:
            src_lbl = os.path.join(src_labels, label_name)
            if os.path.isfile(src_lbl):
                shutil.copy2(src_lbl, os.path.join(tgt_labels, label_name))

        merged += 1

    return merged


def merge_manual_images(extra_dir: str, target_dir: str) -> int:
    """
    Merge manually-provided images into the training set.

    Expects extra_dir to contain images (and optionally a labels/ subfolder).
    """
    if not os.path.isdir(extra_dir):
        logger.warning(f"Extra directory not found: {extra_dir}")
        return 0

    tgt_images = os.path.join(target_dir, "train", "images")
    tgt_labels = os.path.join(target_dir, "train", "labels")
    os.makedirs(tgt_images, exist_ok=True)
    os.makedirs(tgt_labels, exist_ok=True)

    labels_dir = os.path.join(extra_dir, "labels")
    has_labels = os.path.isdir(labels_dir)

    merged = 0
    for img_file in os.listdir(extra_dir):
        img_ext = os.path.splitext(img_file)[1].lower()
        if img_ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            continue

        src_img = os.path.join(extra_dir, img_file)
        tgt_img = os.path.join(tgt_images, img_file)

        if os.path.exists(tgt_img):
            continue

        shutil.copy2(src_img, tgt_img)

        # Copy label if available
        if has_labels:
            label_name = os.path.splitext(img_file)[0] + ".txt"
            src_lbl = os.path.join(labels_dir, label_name)
            if os.path.isfile(src_lbl):
                shutil.copy2(src_lbl, os.path.join(tgt_labels, label_name))

        merged += 1

    return merged


def main():
    parser = argparse.ArgumentParser(
        description="Expand FloodWatch training dataset"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ROBOFLOW_API_KEY", ""),
        help="Roboflow API key (or set ROBOFLOW_API_KEY env var)",
    )
    parser.add_argument(
        "--extra-dir",
        default=None,
        help="Path to directory with additional images to merge",
    )
    parser.add_argument(
        "--target", default=DATASET_DIR,
        help=f"Target dataset directory (default: {DATASET_DIR})",
    )
    parser.add_argument(
        "--download-dir",
        default=os.path.join(PROJECT_ROOT, "data", "_downloads"),
        help="Temporary directory for downloaded datasets",
    )
    args = parser.parse_args()

    # Current counts
    train_before = count_images(os.path.join(args.target, "train", "images"))
    val_before = count_images(os.path.join(args.target, "val", "images"))
    if val_before == 0:
        val_before = count_images(os.path.join(args.target, "valid", "images"))

    print()
    print("=" * 60)
    print("  FloodWatch Dataset Expansion")
    print("=" * 60)
    print(f"\n  Current dataset:")
    print(f"    Train images: {train_before}")
    print(f"    Val images:   {val_before}")
    print(f"    Total:        {train_before + val_before}")

    total_merged = 0

    # Download from Roboflow
    if args.api_key:
        os.makedirs(args.download_dir, exist_ok=True)
        download_results = download_roboflow_datasets(args.api_key, args.download_dir)

        for result in download_results:
            if result["status"] == "success" and result["path"]:
                for split in ("train", "valid", "test"):
                    n = merge_dataset(result["path"], args.target, split)
                    if n > 0:
                        logger.info(f"  Merged {n} images from {result['name']} ({split})")
                        total_merged += n
    else:
        logger.warning(
            "No Roboflow API key provided. Set ROBOFLOW_API_KEY env var or use --api-key. "
            "Skipping Roboflow downloads."
        )

    # Merge manual images
    if args.extra_dir:
        n = merge_manual_images(args.extra_dir, args.target)
        logger.info(f"  Merged {n} manual images from {args.extra_dir}")
        total_merged += n

    # Final counts
    train_after = count_images(os.path.join(args.target, "train", "images"))
    val_after = count_images(os.path.join(args.target, "val", "images"))
    if val_after == 0:
        val_after = count_images(os.path.join(args.target, "valid", "images"))

    print(f"\n  After expansion:")
    print(f"    Train images: {train_after}")
    print(f"    Val images:   {val_after}")
    print(f"    Total:        {train_after + val_after}")
    print(f"    New images:   {total_merged}")

    target_total = 1200
    current = train_after + val_after
    if current >= target_total:
        print(f"\n  ✅ Target reached: {current} ≥ {target_total}")
    else:
        print(f"\n  ⚠️  Need {target_total - current} more images to reach target of {target_total}")
        print(f"     Use --extra-dir to add manually collected images")

    print("=" * 60)


if __name__ == "__main__":
    main()
