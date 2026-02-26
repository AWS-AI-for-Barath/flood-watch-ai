"""
video_utils.py — Frame extraction from video or image input.

Supports:
  - Images: .jpg, .jpeg, .png, .bmp
  - Videos: .mp4, .avi, .mov

Extracts a single representative frame for downstream analysis using a
configurable strategy (first, middle, last).
"""

import logging
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov"}
VALID_STRATEGIES = {"first", "middle", "last"}


def extract_frame(
    input_path: str,
    strategy: str = "middle",
) -> np.ndarray:
    """
    Extract a representative frame from a video or load an image directly.

    Args:
        input_path: Path to a local video or image file.
        strategy: Frame extraction strategy for videos —
                  "first", "middle" (default), or "last".
                  Ignored for image inputs.

    Returns:
        A BGR numpy array (OpenCV format) of the extracted frame.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If the file extension is not supported, the strategy
                    is invalid, or the media is unreadable.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if strategy not in VALID_STRATEGIES:
        raise ValueError(
            f"Invalid strategy '{strategy}'. Must be one of: {sorted(VALID_STRATEGIES)}"
        )

    ext = os.path.splitext(input_path)[1].lower()

    if ext in IMAGE_EXTENSIONS:
        logger.info(f"Media type: image ({ext})")
        return _load_image(input_path)
    elif ext in VIDEO_EXTENSIONS:
        logger.info(f"Media type: video ({ext}) — strategy: {strategy}")
        return _extract_video_frame(input_path, strategy)
    else:
        supported = sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)
        raise ValueError(
            f"Unsupported file format '{ext}'. Supported formats: {supported}"
        )


def _load_image(path: str) -> np.ndarray:
    """Load an image file using OpenCV."""
    frame = cv2.imread(path)
    if frame is None:
        raise ValueError(f"Failed to read image (file may be corrupted): {path}")
    logger.info(f"Image loaded: {frame.shape[1]}x{frame.shape[0]} px")
    return frame


def _extract_video_frame(path: str, strategy: str) -> np.ndarray:
    """Extract a frame from a video file using the given strategy."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Failed to open video (file may be corrupted or unreadable): {path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError(f"Video has no readable frames: {path}")

        # Determine target frame index based on strategy
        if strategy == "first":
            target_frame = 0
        elif strategy == "last":
            target_frame = max(0, total_frames - 1)
        else:  # middle
            target_frame = total_frames // 2

        logger.info(
            f"Video: {total_frames} frames total — extracting frame {target_frame} "
            f"(strategy: {strategy})"
        )

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        ret, frame = cap.read()
        if not ret or frame is None:
            raise ValueError(
                f"Failed to read frame {target_frame} from video: {path}"
            )

        logger.info(f"Frame extracted: {frame.shape[1]}x{frame.shape[0]} px")
        return frame
    finally:
        cap.release()
