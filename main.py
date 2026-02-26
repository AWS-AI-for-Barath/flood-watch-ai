"""
main.py — CLI entry point for FloodWatch AI.

Usage:
    python main.py input.mp4 --output result.json
    python main.py flood_photo.jpg
    python main.py flood_clip.mp4 --strategy first --output result.json
"""

import argparse
import json
import logging
import os
import sys

from src.lambda_handler import handle_media_input
from src.video_utils import VIDEO_EXTENSIONS


def main():
    parser = argparse.ArgumentParser(
        prog="floodwatch",
        description="FloodWatch AI — Multimodal Flood Scene Analysis",
        epilog="Example: python main.py flood_video.mp4 --output result.json",
    )
    parser.add_argument(
        "input",
        help="Path to a local flood video (.mp4) or image (.jpg/.png)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Path to write the JSON result file (optional)",
        default=None,
    )
    parser.add_argument(
        "--strategy", "-s",
        choices=["first", "middle", "last"],
        default="middle",
        help="Frame extraction strategy for video input (default: middle)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Log media type
    ext = os.path.splitext(args.input)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        logging.getLogger(__name__).info(
            "Processing video input → extracting representative frame"
        )

    # Use Lambda handler as shared entry point
    response = handle_media_input(
        args.input,
        output_path=args.output,
        strategy=args.strategy,
    )

    if response["status"] == "success":
        print(json.dumps(response["data"], indent=2))
    else:
        print(f"Error: {response['message']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
