"""
pipeline.py — Fusion pipeline for FloodWatch AI.

Orchestrates frame extraction, Nova semantic analysis, and YOLO depth
estimation, then fuses results into a unified JSON output.
"""

import json
import logging
import os

from src.nova_client import analyze_flood_scene
from src.video_utils import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, extract_frame
from src.yolo_detector import estimate_depth

logger = logging.getLogger(__name__)


def run_pipeline(
    input_path: str,
    output_path: str | None = None,
    strategy: str = "middle",
) -> dict:
    """
    Run the full FloodWatch analysis pipeline.

    Args:
        input_path: Path to a local video or image file.
        output_path: Optional path to write the JSON result.
        strategy: Frame extraction strategy for videos (first/middle/last).

    Returns:
        Unified result dict combining Nova and YOLO outputs.
    """
    logger.info(f"Starting pipeline for: {input_path}")

    # Detect and log media type
    ext = os.path.splitext(input_path)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        media_type = "video"
        logger.info(f"Media type: video ({ext}) — frame strategy: {strategy}")
    elif ext in IMAGE_EXTENSIONS:
        media_type = "image"
        logger.info(f"Media type: image ({ext})")
    else:
        media_type = "unknown"
        logger.info(f"Media type: unknown ({ext})")

    # Step 1: Extract frame
    logger.info("Extracting representative frame...")
    frame = extract_frame(input_path, strategy=strategy)
    logger.info(f"Frame extracted: {frame.shape[1]}x{frame.shape[0]} px")

    # Step 2: Nova semantic analysis
    logger.info("Running Nova flood scene analysis...")
    try:
        nova_result = analyze_flood_scene(frame)
        logger.info(f"Nova analysis complete — severity: {nova_result.get('severity')}")
    except RuntimeError as e:
        logger.error(f"Nova analysis failed: {e}")
        nova_result = {
            "people_trapped": False,
            "vehicles_submerged": False,
            "infrastructure_damage": False,
            "severity": "unknown",
            "description": f"Nova analysis unavailable: {e}",
        }

    # Step 3: YOLO depth estimation
    logger.info("Running YOLOv8 depth estimation...")
    yolo_result = estimate_depth(frame)
    logger.info(
        f"YOLO estimate: {yolo_result.get('water_depth_cm')} cm "
        f"({yolo_result.get('reference_object')})"
    )

    # Step 4: Fuse results
    result = {
        "input_file": os.path.basename(input_path),
        "water_depth_cm": yolo_result["water_depth_cm"],
        "severity": nova_result["severity"],
        "people_trapped": nova_result["people_trapped"],
        "vehicles_submerged": nova_result["vehicles_submerged"],
        "infrastructure_damage": nova_result["infrastructure_damage"],
        "reference_object": yolo_result["reference_object"],
        "confidence": yolo_result["confidence"],
        "description": nova_result["description"],
    }

    # Write to file if output path specified
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Result written to: {output_path}")

    return result
