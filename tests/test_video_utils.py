"""Tests for src/video_utils.py — frame extraction."""

import os
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.video_utils import extract_frame


# ---------------------------------------------------------------------------
# Image tests
# ---------------------------------------------------------------------------

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

    @patch("src.video_utils.cv2.imread")
    def test_extract_frame_image_mock(self, mock_imread, tmp_path):
        """Should return the frame from cv2.imread (mocked)."""
        fake_frame = np.zeros((200, 300, 3), dtype=np.uint8)
        mock_imread.return_value = fake_frame

        path = str(tmp_path / "flood.jpg")
        with open(path, "w") as f:
            f.write("")  # dummy file so os.path.isfile passes

        result = extract_frame(path)
        mock_imread.assert_called_once_with(path)
        assert result is fake_frame


# ---------------------------------------------------------------------------
# Video tests
# ---------------------------------------------------------------------------

class TestExtractFrameVideo:
    """Test video loading with mocked VideoCapture."""

    @patch("src.video_utils.cv2.VideoCapture")
    def test_extract_frame_video_middle(self, mock_vc_cls, tmp_path):
        """Should extract the middle frame from a video."""
        fake_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 100.0  # 100 total frames
        mock_cap.read.return_value = (True, fake_frame)
        mock_vc_cls.return_value = mock_cap

        path = str(tmp_path / "flood.mp4")
        with open(path, "w") as f:
            f.write("")

        result = extract_frame(path, strategy="middle")

        # Should seek to frame 50 (100 // 2)
        mock_cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 50)
        assert result is fake_frame
        mock_cap.release.assert_called_once()

    @patch("src.video_utils.cv2.VideoCapture")
    def test_extract_frame_video_first(self, mock_vc_cls, tmp_path):
        """Should extract the first frame when strategy='first'."""
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 100.0
        mock_cap.read.return_value = (True, fake_frame)
        mock_vc_cls.return_value = mock_cap

        path = str(tmp_path / "flood.mp4")
        with open(path, "w") as f:
            f.write("")

        result = extract_frame(path, strategy="first")

        mock_cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 0)
        assert result is fake_frame

    @patch("src.video_utils.cv2.VideoCapture")
    def test_extract_frame_video_last(self, mock_vc_cls, tmp_path):
        """Should extract the last frame when strategy='last'."""
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 100.0
        mock_cap.read.return_value = (True, fake_frame)
        mock_vc_cls.return_value = mock_cap

        path = str(tmp_path / "flood.mp4")
        with open(path, "w") as f:
            f.write("")

        result = extract_frame(path, strategy="last")

        mock_cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 99)
        assert result is fake_frame

    @patch("src.video_utils.cv2.VideoCapture")
    def test_extract_frame_video_unreadable(self, mock_vc_cls, tmp_path):
        """Should raise ValueError when video cannot be opened."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc_cls.return_value = mock_cap

        path = str(tmp_path / "bad.mp4")
        with open(path, "w") as f:
            f.write("")

        with pytest.raises(ValueError, match="Failed to open video"):
            extract_frame(path)

        mock_cap.release.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

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

    def test_invalid_strategy(self, tmp_path):
        """Should raise ValueError for invalid strategy."""
        path = str(tmp_path / "test.jpg")
        with open(path, "w") as f:
            f.write("")

        with pytest.raises(ValueError, match="Invalid strategy"):
            extract_frame(path, strategy="random")

    def test_corrupted_image(self, tmp_path):
        """Should raise ValueError for unreadable image data."""
        path = str(tmp_path / "corrupt.jpg")
        with open(path, "wb") as f:
            f.write(b"not a real jpeg")

        with pytest.raises(ValueError, match="Failed to read image"):
            extract_frame(path)
