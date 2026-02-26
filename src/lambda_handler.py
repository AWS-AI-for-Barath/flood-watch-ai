"""
lambda_handler.py — Lambda-ready wrapper for FloodWatch AI pipeline.

Provides a safe entry point that never raises unhandled exceptions.
Returns a structured envelope with status, data, and error message.

This module is used by both the CLI (main.py) and will serve as the
AWS Lambda handler entry point when deployed.
"""

import logging

from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def handle_media_input(
    input_path: str,
    output_path: str | None = None,
    strategy: str = "middle",
) -> dict:
    """
    Lambda-ready wrapper for FloodWatch multimodal pipeline.

    Args:
        input_path: Local path to flood image or video.
        output_path: Optional path to write the JSON result.
        strategy: Frame extraction strategy for videos (first/middle/last).

    Returns:
        {
            "status": "success" | "error",
            "data": {pipeline_output} on success,
            "message": "error description" on failure
        }
    """
    try:
        logger.info(f"Lambda handler invoked for: {input_path}")
        result = run_pipeline(input_path, output_path=output_path, strategy=strategy)
        logger.info("Pipeline completed successfully.")
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {type(e).__name__}: {e}")
        return {
            "status": "error",
            "message": f"{type(e).__name__}: {e}",
        }
