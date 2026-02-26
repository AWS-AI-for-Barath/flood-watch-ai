"""
validation.py — Depth detection validation utility for FloodWatch AI.

Confirms that YOLO depth estimation returns non-null results when
a detectable reference object is present in the scene.
"""

import logging

from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def validate_depth_detection(input_path: str) -> dict:
    """
    Run the pipeline and verify whether water depth was estimated
    from a detected reference object.

    Args:
        input_path: Local path to flood image or video.

    Returns:
        {
            "depth_detected": bool,
            "reference_object": str | None,
            "water_depth_cm": float | None
        }
    """
    logger.info(f"Validating depth detection for: {input_path}")

    result = run_pipeline(input_path)

    depth = result.get("water_depth_cm")
    ref_obj = result.get("reference_object")
    detected = depth is not None

    summary = {
        "depth_detected": detected,
        "reference_object": ref_obj,
        "water_depth_cm": depth,
    }

    if detected:
        logger.info(
            f"Depth detected: {depth} cm via {ref_obj}"
        )
    else:
        logger.warning("No reference object detected — depth is null.")

    return summary
