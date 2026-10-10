"""Tests for images.inspect."""

from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageFile, features

from pixgen.images.inspect import has_codec, inspect_header, load_image
from pixgen.images.models import ImageFormat, ImageInputError, LocalImage

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

    def test_load_avif_when_available(self, tmp_path: Path) -> None:
        if not has_codec(ImageFormat.AVIF, encode=True):
            return
        path = tmp_path / "photo.avif"
        path.write_bytes(_encode("AVIF"))
        assert load_image(path).media_type == "image/avif"
        assert ImageFormat.AVIF.extension == "avif"

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

    def test_header_only_load_skips_stream_verification(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / "photo.png"
        path.write_bytes(_encode("PNG"))

        def reject_verify(_image) -> None:
            raise AssertionError("verified the encoded stream")

        monkeypatch.setattr(Image.Image, "verify", reject_verify)
        assert load_image(path, verify=False).media_type == "image/png"

    def test_preserves_original_bytes(self, tmp_path: Path, png_bytes: bytes) -> None:
        path = tmp_path / "test.png"
        path.write_bytes(png_bytes)
        result = load_image(path)
        assert result.content == png_bytes
        assert result.content is not png_bytes


class TestFormatCapabilities:
    @pytest.mark.parametrize(
        ("image_format", "feature"),
        [
            (ImageFormat.AVIF, "avif"),
            (ImageFormat.WEBP, "webp"),
            (ImageFormat.JPEG, "jpg"),
            (ImageFormat.PNG, "zlib"),
        ],
        ids=str,
    )
    @pytest.mark.parametrize("encode", [False, True], ids=["read", "write"])
    def test_registered_codec_requires_available_feature(
        self, monkeypatch, image_format, feature, encode
    ) -> None:
        Image.init()
        registry = Image.SAVE if encode else Image.OPEN
        monkeypatch.setitem(registry, image_format.pillow_name, registry["PNG"])
        monkeypatch.setattr(features, "check", lambda name: name != feature)
        assert not has_codec(image_format, encode=encode)

    @pytest.mark.parametrize("encode", [False, True], ids=["read", "write"])
    def test_missing_registration_is_unavailable(self, monkeypatch, encode) -> None:
        Image.init()
        monkeypatch.delitem(Image.SAVE if encode else Image.OPEN, "AVIF", raising=False)
        assert not has_codec(ImageFormat.AVIF, encode=encode)


def _local(path: Path) -> LocalImage:
    return load_image(path, verify=False)


class TestInspectHeader:
    def test_reads_facts_without_decoding_pixels(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / "photo.png"
        Image.new("RGBA", (30, 20)).save(path, icc_profile=b"profile")
        image = _local(path)

        def reject_load(_image, *args, **kwargs) -> None:
            raise AssertionError("decoded source pixels")

        monkeypatch.setattr(ImageFile.ImageFile, "load", reject_load)
        facts = inspect_header(image)
        assert (facts.format, facts.width, facts.height) == (ImageFormat.PNG, 30, 20)
        assert (facts.mode, facts.has_alpha, facts.icc_profile) == ("RGBA", True, b"profile")

    @pytest.mark.parametrize("fmt", ["JPEG", "PNG"], ids=str.lower)
    def test_swaps_dimensions_for_rotated_orientation(self, tmp_path: Path, fmt) -> None:
        path = tmp_path / "rotated"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (100, 200)).save(path, format=fmt, exif=exif)
        facts = inspect_header(_local(path))
        assert (facts.width, facts.height) == (200, 100)

    def test_palette_colour_key_counts_as_alpha(self, tmp_path: Path) -> None:
        path = tmp_path / "palette.png"
        Image.new("P", (2, 2)).save(path, transparency=0)
        facts = inspect_header(_local(path))
        assert (facts.mode, facts.has_alpha) == ("P", True)

    def test_rejects_animation(self, tmp_path: Path) -> None:
        path = tmp_path / "animated.png"
        Image.new("RGB", (2, 2), "red").save(
            path, save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")]
        )
        with pytest.raises(ImageInputError, match="animated") as exc_info:
            inspect_header(_local(path))
        assert exc_info.value.path == path
