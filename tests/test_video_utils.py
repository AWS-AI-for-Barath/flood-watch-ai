"""Tests for src/video_utils.py — frame extraction."""

import os
import tempfile

import cv2
import numpy as np
import pytest

from src.video_utils import extract_frame


class TestExtractFrameImage:
    """Test image loading path."""

    def test_loads_valid_jpg(self, tmp_path):
        """Should load a valid JPEG image and return a numpy array."""
        img = np.random.randint(0, 255, (100, 150, 3), dtype=np.uint8)
        path = str(tmp_path / "test.jpg")
        cv2.imwrite(path, img)

        result = extract_frame(path)
        assert isinstance(result, np.ndarray)
        assert result.shape == (100, 150, 3)

    def test_loads_valid_png(self, tmp_path):
        """Should load a valid PNG image."""
        img = np.zeros((50, 80, 3), dtype=np.uint8)
        path = str(tmp_path / "test.png")
        cv2.imwrite(path, img)

        result = extract_frame(path)
        assert result.shape == (50, 80, 3)


class TestExtractFrameErrors:
    """Test error handling."""

    def test_file_not_found(self):
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError, match="not found"):
            extract_frame("nonexistent_file.jpg")

    def test_unsupported_format(self, tmp_path):
        """Should raise ValueError for unsupported extensions."""
        path = str(tmp_path / "test.txt")
        with open(path, "w") as f:
            f.write("not an image")

        with pytest.raises(ValueError, match="Unsupported file format"):
            extract_frame(path)

    def test_corrupted_image(self, tmp_path):
        """Should raise RuntimeError for unreadable image data."""
        path = str(tmp_path / "corrupt.jpg")
        with open(path, "wb") as f:
            f.write(b"not a real jpeg")

        with pytest.raises(RuntimeError, match="Failed to read image"):
            extract_frame(path)
