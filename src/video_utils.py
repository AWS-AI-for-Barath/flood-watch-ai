"""
video_utils.py — Frame extraction from video or image input.

Supports:
  - Images: .jpg, .jpeg, .png, .bmp
  - Videos: .mp4, .avi, .mov

Extracts a single representative frame for downstream analysis.
"""

import os

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov"}


def extract_frame(input_path: str) -> np.ndarray:
    """
    Extract a representative frame from a video or load an image directly.

    Args:
        input_path: Path to a local video or image file.

    Returns:
        A BGR numpy array (OpenCV format) of the extracted frame.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If the file extension is not supported.
        RuntimeError: If the media file cannot be read.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    ext = os.path.splitext(input_path)[1].lower()

    if ext in IMAGE_EXTENSIONS:
        return _load_image(input_path)
    elif ext in VIDEO_EXTENSIONS:
        return _extract_video_frame(input_path)
    else:
        supported = sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)
        raise ValueError(
            f"Unsupported file format '{ext}'. Supported formats: {supported}"
        )


def _load_image(path: str) -> np.ndarray:
    """Load an image file using OpenCV."""
    frame = cv2.imread(path)
    if frame is None:
        raise RuntimeError(f"Failed to read image: {path}")
    return frame


def _extract_video_frame(path: str) -> np.ndarray:
    """Extract the middle frame from a video file."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise RuntimeError(f"Video has no readable frames: {path}")

        # Seek to the middle frame for a representative sample
        middle = total_frames // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, middle)

        ret, frame = cap.read()
        if not ret or frame is None:
            raise RuntimeError(
                f"Failed to read frame {middle} from video: {path}"
            )

        return frame
    finally:
        cap.release()
