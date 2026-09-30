"""Tests for images.inspect."""

from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from pixgen.images.inspect import load_image
from pixgen.images.models import ImageInputError, LocalImage

if TYPE_CHECKING:
    from pathlib import Path


def _encode(fmt: str) -> bytes:
    """Encode a minimal 1x1 image in the given Pillow format."""
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    """Minimal valid PNG file bytes."""
    return _encode("PNG")


@pytest.fixture
def jpeg_bytes() -> bytes:
    """Minimal valid JPEG file bytes."""
    return _encode("JPEG")


@pytest.fixture
def webp_bytes() -> bytes:
    """Minimal valid WebP file bytes."""
    return _encode("WEBP")


class TestLoadImage:
    """Tests for load_image function."""

    def test_load_png(self, tmp_path: Path, png_bytes: bytes) -> None:
        path = tmp_path / "test.png"
        path.write_bytes(png_bytes)
        result = load_image(path)
        assert isinstance(result, LocalImage)
        assert result.source_path == path
        assert result.filename == "test.png"
        assert result.content == png_bytes
        assert result.media_type == "image/png"
        assert result.byte_size == len(png_bytes)

    def test_load_jpeg(self, tmp_path: Path, jpeg_bytes: bytes) -> None:
        path = tmp_path / "photo.jpg"
        path.write_bytes(jpeg_bytes)
        result = load_image(path)
        assert result.media_type == "image/jpeg"

    def test_load_webp(self, tmp_path: Path, webp_bytes: bytes) -> None:
        path = tmp_path / "image.webp"
        path.write_bytes(webp_bytes)
        result = load_image(path)
        assert result.media_type == "image/webp"

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.png"
        with pytest.raises(ImageInputError, match="does not exist"):
            load_image(path)

    def test_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ImageInputError, match="does not exist"):
            load_image(tmp_path)

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.png"
        path.write_bytes(b"")
        with pytest.raises(ImageInputError, match="empty"):
            load_image(path)

    def test_oversize_file_raises(self, tmp_path: Path, png_bytes: bytes) -> None:
        path = tmp_path / "large.png"
        path.write_bytes(png_bytes)
        with pytest.raises(ImageInputError, match="exceeds limit"):
            load_image(path, max_bytes=10)

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "unknown.xyz"
        path.write_bytes(b"not an image")
        with pytest.raises(ImageInputError, match="unrecognised"):
            load_image(path)

    def test_truncated_image_raises(self, tmp_path: Path, png_bytes: bytes) -> None:
        path = tmp_path / "corrupt.png"
        path.write_bytes(png_bytes[:-20])
        with pytest.raises(ImageInputError, match="corrupt"):
            load_image(path)

    def test_preserves_original_bytes(self, tmp_path: Path, png_bytes: bytes) -> None:
        path = tmp_path / "test.png"
        path.write_bytes(png_bytes)
        result = load_image(path)
        assert result.content == png_bytes
        assert result.content is not png_bytes
