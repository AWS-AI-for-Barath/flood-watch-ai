"""
audit_labels.py — Automated YOLO label quality auditing and repair.

Scans all label files in the flood dataset and detects:
  - Empty labels (no annotations)
  - Extremely small bounding boxes (area < 0.001)
  - Boxes with coordinates outside [0, 1] range
  - Duplicate boxes (IoU > 0.95)
  - Invalid class IDs (not in allowed set)

Usage:
    python scripts/audit_labels.py                # Dry run (report only)
    python scripts/audit_labels.py --fix          # Auto-fix issues
    python scripts/audit_labels.py --fix --report audit_report.json
"""

import argparse
import json
import logging
import os
import sys
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "flood_dataset")

# Valid class IDs (must match flood_dataset.yaml)
VALID_CLASS_IDS = {0, 1, 2, 3, 4, 5}

# Minimum box area (fraction of image) to keep
MIN_BOX_AREA = 0.001

# IoU threshold for duplicate detection
DUPLICATE_IOU_THRESHOLD = 0.95


def parse_yolo_line(line: str) -> tuple | None:
    """Parse a YOLO annotation line into (class_id, x_center, y_center, w, h)."""
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        cls_id = int(parts[0])
        x_c = float(parts[1])
        y_c = float(parts[2])
        w = float(parts[3])
        h = float(parts[4])
        return (cls_id, x_c, y_c, w, h)
    except (ValueError, IndexError):
        return None


def compute_iou(box1: tuple, box2: tuple) -> float:
    """Compute IoU between two YOLO boxes (x_c, y_c, w, h)."""
    _, x1, y1, w1, h1 = box1
    _, x2, y2, w2, h2 = box2

    # Convert to corners
    ax1, ay1 = x1 - w1 / 2, y1 - h1 / 2
    ax2, ay2 = x1 + w1 / 2, y1 + h1 / 2
    bx1, by1 = x2 - w2 / 2, y2 - h2 / 2
    bx2, by2 = x2 + w2 / 2, y2 + h2 / 2

    # Intersection
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    area1 = w1 * h1
    area2 = w2 * h2
    union = area1 + area2 - inter

    return inter / union if union > 0 else 0.0


def audit_label_file(filepath: str) -> dict:
    """
    Audit a single YOLO label file and return issues found.

    Returns dict with:
        - issues: list of issue dicts
        - fixed_lines: list of repaired annotation strings (if fixable)
        - original_count: number of original annotations
    """
    issues = []
    fixed_lines = []

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Parse all annotations
    annotations = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        parsed = parse_yolo_line(stripped)
        if parsed is None:
            issues.append({"type": "malformed", "line": i + 1, "content": stripped})
            continue
        annotations.append(parsed)

    original_count = len(annotations)

    # Check: empty labels
    if not annotations:
        issues.append({"type": "empty_label", "file": os.path.basename(filepath)})
        return {"issues": issues, "fixed_lines": [], "original_count": 0}

    # Process each annotation
    kept = []
    for ann in annotations:
        cls_id, x_c, y_c, w, h = ann

        # Check: invalid class ID
        if cls_id not in VALID_CLASS_IDS:
            issues.append({
                "type": "invalid_class",
                "class_id": cls_id,
                "file": os.path.basename(filepath),
            })
            continue  # Skip this annotation

        # Check: out of bounds → clamp
        clamped = False
        if x_c < 0 or x_c > 1 or y_c < 0 or y_c > 1:
            x_c = max(0.0, min(1.0, x_c))
            y_c = max(0.0, min(1.0, y_c))
            clamped = True

        # Clamp width/height to keep box within image
        if x_c - w / 2 < 0:
            w = x_c * 2
            clamped = True
        if x_c + w / 2 > 1:
            w = (1 - x_c) * 2
            clamped = True
        if y_c - h / 2 < 0:
            h = y_c * 2
            clamped = True
        if y_c + h / 2 > 1:
            h = (1 - y_c) * 2
            clamped = True

        if clamped:
            issues.append({
                "type": "out_of_bounds",
                "file": os.path.basename(filepath),
            })

        # Check: extremely small box
        area = w * h
        if area < MIN_BOX_AREA:
            issues.append({
                "type": "tiny_box",
                "area": round(area, 6),
                "file": os.path.basename(filepath),
            })
            continue  # Remove tiny boxes

        kept.append((cls_id, x_c, y_c, w, h))

    # Check: duplicate boxes (IoU > threshold)
    final = []
    for i, box in enumerate(kept):
        is_duplicate = False
        for j, existing in enumerate(final):
            if box[0] == existing[0] and compute_iou(box, existing) > DUPLICATE_IOU_THRESHOLD:
                is_duplicate = True
                issues.append({
                    "type": "duplicate",
                    "file": os.path.basename(filepath),
                })
                break
        if not is_duplicate:
            final.append(box)

    # Build fixed lines
    for cls_id, x_c, y_c, w, h in final:
        fixed_lines.append(f"{cls_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}")

    return {
        "issues": issues,
        "fixed_lines": fixed_lines,
        "original_count": original_count,
    }


def audit_dataset(dataset_dir: str, fix: bool = False) -> dict:
    """
    Audit all label files in a dataset directory.

    Args:
        dataset_dir: Root dataset directory (containing train/, val/, etc.)
        fix: If True, write corrected labels back to disk.

    Returns:
        Summary report dict.
    """
    summary = defaultdict(int)
    all_issues = []
    files_fixed = 0
    files_removed = 0

    label_dirs = []
    for split in ("train", "val", "valid", "test"):
        lbl_dir = os.path.join(dataset_dir, split, "labels")
        if os.path.isdir(lbl_dir):
            label_dirs.append((split, lbl_dir))

    for split, lbl_dir in label_dirs:
        logger.info(f"Auditing {split} labels in {lbl_dir}")

        for fname in sorted(os.listdir(lbl_dir)):
            if not fname.endswith(".txt"):
                continue

            filepath = os.path.join(lbl_dir, fname)
            result = audit_label_file(filepath)

            for issue in result["issues"]:
                summary[issue["type"]] += 1
                all_issues.append({**issue, "split": split})

            if result["issues"] and fix:
                if not result["fixed_lines"]:
                    # Remove empty label files and their images
                    os.remove(filepath)
                    files_removed += 1
                    # Optionally remove corresponding image
                    for ext in (".jpg", ".jpeg", ".png"):
                        img_path = filepath.replace(
                            os.sep + "labels" + os.sep,
                            os.sep + "images" + os.sep,
                        ).replace(".txt", ext)
                        if os.path.isfile(img_path):
                            os.remove(img_path)
                            break
                else:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write("\n".join(result["fixed_lines"]) + "\n")
                    files_fixed += 1

    report = {
        "total_issues": sum(summary.values()),
        "issues_by_type": dict(summary),
        "files_fixed": files_fixed,
        "files_removed": files_removed,
        "details": all_issues[:100],  # Cap details for readability
    }

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Audit and repair YOLO label annotations"
    )
    parser.add_argument(
        "--dataset", default=DATASET_DIR,
        help=f"Dataset root directory (default: {DATASET_DIR})",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Auto-fix issues (otherwise dry-run only)",
    )
    parser.add_argument(
        "--report", default=None,
        help="Save JSON report to file",
    )
    args = parser.parse_args()

    mode = "FIX" if args.fix else "DRY RUN"
    print()
    print("=" * 60)
    print(f"  FloodWatch Label Audit ({mode})")
    print("=" * 60)

    report = audit_dataset(args.dataset, fix=args.fix)

    print(f"\n  Issues found: {report['total_issues']}")
    for issue_type, count in sorted(report["issues_by_type"].items()):
        print(f"    {issue_type:20s}: {count}")

    if args.fix:
        print(f"\n  Files fixed:   {report['files_fixed']}")
        print(f"  Files removed: {report['files_removed']}")
    else:
        print(f"\n  Run with --fix to auto-repair issues")

    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"  Report saved to: {args.report}")

    print("=" * 60)


if __name__ == "__main__":
    main()
