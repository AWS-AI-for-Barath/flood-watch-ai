"""
normalize_labels.py — Convert segmentation polygon labels to YOLO bounding boxes.

YOLO detection training expects labels in the format:
    class x_center y_center width height

But some datasets (e.g., from Roboflow) export segmentation polygons:
    class x1 y1 x2 y2 x3 y3 ... xN yN

This script converts all polygon annotations to their bounding box equivalents
by computing the min/max of polygon coordinates.

Usage:
    python scripts/normalize_labels.py                    # Dry run
    python scripts/normalize_labels.py --fix              # Convert in-place
    python scripts/normalize_labels.py --fix --backup     # Convert + keep originals
"""

import argparse
import logging
import os
import shutil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "flood_dataset")


def polygon_to_bbox(parts: list[str]) -> str | None:
    """
    Convert a segmentation polygon line to YOLO bounding box format.

    Input:  ['class', 'x1', 'y1', 'x2', 'y2', ..., 'xN', 'yN']
    Output: 'class x_center y_center width height'

    Returns None if the line can't be parsed.
    """
    if len(parts) < 5:
        return None

    try:
        cls_id = int(parts[0])
        coords = [float(v) for v in parts[1:]]
    except (ValueError, IndexError):
        return None

    # Must have even number of coordinates (x,y pairs)
    if len(coords) % 2 != 0:
        return None

    xs = coords[0::2]  # Even indices = x coordinates
    ys = coords[1::2]  # Odd indices = y coordinates

    if not xs or not ys:
        return None

    x_min = max(0.0, min(xs))
    x_max = min(1.0, max(xs))
    y_min = max(0.0, min(ys))
    y_max = min(1.0, max(ys))

    width = x_max - x_min
    height = y_max - y_min

    if width <= 0 or height <= 0:
        return None

    x_center = x_min + width / 2
    y_center = y_min + height / 2

    return f"{cls_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


def normalize_label_file(filepath: str) -> dict:
    """
    Normalize a single label file: convert polygon lines to bbox format.

    Returns:
        Dict with conversion stats for this file.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    stats = {"total": 0, "polygons": 0, "bboxes": 0, "invalid": 0}
    converted_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        parts = stripped.split()
        stats["total"] += 1

        if len(parts) == 5:
            # Already in bbox format
            stats["bboxes"] += 1
            converted_lines.append(stripped)
        elif len(parts) > 5:
            # Polygon → convert to bbox
            bbox_line = polygon_to_bbox(parts)
            if bbox_line:
                stats["polygons"] += 1
                converted_lines.append(bbox_line)
            else:
                stats["invalid"] += 1
        else:
            stats["invalid"] += 1

    return {
        "stats": stats,
        "converted_lines": converted_lines,
    }


def normalize_dataset(dataset_dir: str, fix: bool = False, backup: bool = False) -> dict:
    """
    Normalize all label files in the dataset.

    Args:
        dataset_dir: Root dataset directory.
        fix: If True, write converted labels back to disk.
        backup: If True and fix is True, save originals to .bak files.

    Returns:
        Summary report dict.
    """
    total_files = 0
    total_polygons = 0
    total_bboxes = 0
    total_invalid = 0
    files_converted = 0

    for split in ("train", "val", "valid", "test"):
        lbl_dir = os.path.join(dataset_dir, split, "labels")
        if not os.path.isdir(lbl_dir):
            continue

        files = sorted(f for f in os.listdir(lbl_dir) if f.endswith(".txt"))
        logger.info(f"Scanning {split}: {len(files)} label files")

        for fname in files:
            filepath = os.path.join(lbl_dir, fname)
            result = normalize_label_file(filepath)

            stats = result["stats"]
            total_files += 1
            total_polygons += stats["polygons"]
            total_bboxes += stats["bboxes"]
            total_invalid += stats["invalid"]

            if stats["polygons"] > 0 and fix:
                if backup:
                    shutil.copy2(filepath, filepath + ".bak")

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write("\n".join(result["converted_lines"]) + "\n")
                files_converted += 1

    return {
        "total_files": total_files,
        "total_annotations": total_polygons + total_bboxes + total_invalid,
        "polygons_converted": total_polygons,
        "already_bbox": total_bboxes,
        "invalid_removed": total_invalid,
        "files_converted": files_converted,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert segmentation polygon labels to YOLO bounding boxes"
    )
    parser.add_argument(
        "--dataset", default=DATASET_DIR,
        help=f"Dataset root directory (default: {DATASET_DIR})",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Convert labels in-place (otherwise dry-run only)",
    )
    parser.add_argument(
        "--backup", action="store_true",
        help="Keep original files as .bak when fixing",
    )
    args = parser.parse_args()

    mode = "FIX" if args.fix else "DRY RUN"
    print()
    print("=" * 60)
    print(f"  FloodWatch Label Normalization ({mode})")
    print("=" * 60)

    report = normalize_dataset(args.dataset, fix=args.fix, backup=args.backup)

    print(f"\n  Label files scanned:    {report['total_files']}")
    print(f"  Total annotations:      {report['total_annotations']}")
    print(f"  ─────────────────────────────────────")
    print(f"  Polygons → BBox:        {report['polygons_converted']}")
    print(f"  Already BBox:           {report['already_bbox']}")
    print(f"  Invalid (removed):      {report['invalid_removed']}")

    if args.fix:
        print(f"\n  ✅ Files converted: {report['files_converted']}")
    else:
        if report["polygons_converted"] > 0:
            print(f"\n  ⚠️  {report['polygons_converted']} polygon annotations found!")
            print(f"     Run with --fix to convert to bounding boxes")
        else:
            print(f"\n  ✅ All labels are already in bounding box format")

    print("=" * 60)


if __name__ == "__main__":
    main()
