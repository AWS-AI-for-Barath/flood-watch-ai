"""
pipeline.py — Fusion pipeline for FloodWatch AI.

Orchestrates frame extraction, Nova semantic analysis, and YOLO depth
estimation, then fuses results into a unified JSON output.

Schema is enforced on every output via enforce_schema().
"""

import json
import logging
import os

from src.nova_client import analyze_flood_scene
from src.video_utils import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, extract_frame
from src.yolo_detector import estimate_depth

logger = logging.getLogger(__name__)

# ---------- Schema definition ----------

REQUIRED_KEYS = {
    "input_file": str,
    "submergence_ratio": (float, int, type(None)),
    "severity": str,
    "people_trapped": bool,
    "vehicles_submerged": bool,
    "infrastructure_damage": bool,
    "reference_object": (str, type(None)),
    "confidence": (float, int, type(None)),
    "description": str,
}

VALID_SEVERITIES = {"low", "medium", "high", "unknown"}


def enforce_schema(result: dict) -> dict:
    """
    Validate and normalise pipeline output to match the frozen schema.

    - Ensures all required keys are present (fills missing with None/defaults).
    - Enforces severity enum.
    - Guarantees no extra keys leak through.

    Args:
        result: Raw fused pipeline dict.

    Returns:
        Schema-compliant dict with all keys present.
    """
    defaults = {
        "input_file": "",
        "submergence_ratio": None,
        "severity": "unknown",
        "people_trapped": False,
        "vehicles_submerged": False,
        "infrastructure_damage": False,
        "reference_object": None,
        "confidence": None,
        "description": "",
    }

    validated = {}
    for key, expected_type in REQUIRED_KEYS.items():
        value = result.get(key, defaults[key])
        # Fill None for missing optional fields
        if value is None:
            validated[key] = None
        elif not isinstance(value, expected_type):
            logger.warning(
                f"Schema: key '{key}' has type {type(value).__name__}, "
                f"expected {expected_type} — using default"
            )
            validated[key] = defaults[key]
        else:
            validated[key] = value

    # Enforce severity enum
    if validated["severity"] not in VALID_SEVERITIES:
        logger.warning(
            f"Schema: severity '{validated['severity']}' not in "
            f"{VALID_SEVERITIES} — defaulting to 'unknown'"
        )
        validated["severity"] = "unknown"

    return validated


# ---------- Pipeline ----------

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
        Schema-validated result dict combining Nova and YOLO outputs.
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
        f"YOLO estimate: {yolo_result.get('submergence_ratio')} submergence "
        f"({yolo_result.get('reference_object')})"
    )

    # Step 4: Fuse and enforce schema
    result = {
        "input_file": os.path.basename(input_path),
        "submergence_ratio": yolo_result["submergence_ratio"],
        "severity": nova_result["severity"],
        "people_trapped": nova_result["people_trapped"],
        "vehicles_submerged": nova_result["vehicles_submerged"],
        "infrastructure_damage": nova_result["infrastructure_damage"],
        "reference_object": yolo_result["reference_object"],
        "confidence": yolo_result["confidence"],
        "description": nova_result["description"],
    }

    result = enforce_schema(result)

    # Write to file if output path specified
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Result written to: {output_path}")

    return result
