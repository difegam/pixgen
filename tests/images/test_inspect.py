"""Tests for images.inspect."""

from typing import TYPE_CHECKING

import pytest

from pixgen.images.inspect import load_image
from pixgen.images.models import ImageInputError, LocalImage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def png_bytes() -> bytes:
    """Minimal valid PNG file bytes."""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
    )


@pytest.fixture
def jpeg_bytes() -> bytes:
    """Minimal valid JPEG file bytes."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


@pytest.fixture
def webp_bytes() -> bytes:
    """Minimal valid WebP file bytes."""
    return b"RIFF\x00\x00\x00\x00WEBPVP8 \x00\x00\x00\x00"


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

    def test_corrupt_png_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.png"
        path.write_bytes(b"\x89PNG" + b"corrupt data without proper header")
        with pytest.raises(ImageInputError, match="unrecognised"):
            load_image(path)

    def test_preserves_original_bytes(self, tmp_path: Path, png_bytes: bytes) -> None:
        path = tmp_path / "test.png"
        path.write_bytes(png_bytes)
        result = load_image(path)
        assert result.content == png_bytes
        assert result.content is not png_bytes
