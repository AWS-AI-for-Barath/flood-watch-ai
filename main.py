"""
main.py — CLI entry point for FloodWatch AI.

Usage:
    python main.py input.mp4 --output result.json
    python main.py flood_photo.jpg
"""

import argparse
import json
import logging
import sys

from src.pipeline import run_pipeline


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

    try:
        result = run_pipeline(args.input, args.output)
        print(json.dumps(result, indent=2))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
