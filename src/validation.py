"""
validation.py — Submergence detection validation utility for FloodWatch AI.

Confirms that YOLO submergence estimation returns non-null results when
a detectable reference object is present in the scene.
"""

import logging

from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def validate_depth_detection(input_path: str) -> dict:
    """
    Run the pipeline and verify whether submergence was estimated
    from a detected reference object.

    Args:
        input_path: Local path to flood image or video.

    Returns:
        {
            "depth_detected": bool,
            "reference_object": str | None,
            "submergence_ratio": float | None
        }
    """
    logger.info(f"Validating submergence detection for: {input_path}")

    result = run_pipeline(input_path)

    ratio = result.get("submergence_ratio")
    ref_obj = result.get("reference_object")
    detected = ratio is not None

    summary = {
        "depth_detected": detected,
        "reference_object": ref_obj,
        "submergence_ratio": ratio,
    }

    if detected:
        logger.info(
            f"Submergence detected: {ratio:.0%} via {ref_obj}"
        )
    else:
        logger.warning("No reference object detected — submergence is null.")

    return summary
