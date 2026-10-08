"""Test shared image normalisation, resizing, and clean encoding."""

from io import BytesIO

import pytest
from PIL import Image, ImageCms

from pixgen.images.inspect import can_encode_format
from pixgen.images.transform import (
    ColourProfilePolicy,
    DecodedImage,
    ImageTransformError,
    ResizeOperation,
    encode_clean,
    load_normalized,
    resize_pixels,
)


@pytest.fixture
def source() -> DecodedImage:
    with BytesIO() as buffer:
        Image.new("RGB", (80, 40), "red").save(buffer, format="PNG")
        return load_normalized(buffer.getvalue(), policy=ColourProfilePolicy.PRESERVE)


class TestLoadNormalized:
    @pytest.mark.parametrize("policy", list(ColourProfilePolicy), ids=lambda p: p.value)
    def test_retains_transparency_from_png_colour_key(self, policy) -> None:
        with BytesIO() as buffer:
            Image.new("RGB", (2, 2), "red").save(
                buffer,
                format="PNG",
                transparency=(255, 0, 0),
            )
            result = load_normalized(buffer.getvalue(), policy=policy)
        assert result.pixels.mode == "RGBA"
        assert result.pixels.getpixel((0, 0)) == (255, 0, 0, 0)

    def test_applies_orientation_before_dimensions(self) -> None:
        image = Image.new("RGB", (30, 20), "red")
        exif = Image.Exif()
        exif[274] = 6
        with BytesIO() as buffer:
            image.save(buffer, format="JPEG", exif=exif)
            result = load_normalized(buffer.getvalue(), policy=ColourProfilePolicy.PRESERVE)
        assert result.pixels.size == (20, 30)
        assert (result.original_width, result.original_height) == (20, 30)
        assert result.source_format == "JPEG"
        assert result.pixels.getexif().get(274) is None

    def test_rejects_animation(self) -> None:
        with BytesIO() as buffer:
            Image.new("RGB", (2, 2), "red").save(
                buffer,
                format="PNG",
                save_all=True,
                append_images=[Image.new("RGB", (2, 2), "blue")],
                duration=100,
            )
            with pytest.raises(ImageTransformError, match="animated") as exc_info:
                load_normalized(buffer.getvalue(), policy=ColourProfilePolicy.PRESERVE)
        assert "animated" in exc_info.value.reason

    @pytest.mark.parametrize("content", [b"", b"not an image"], ids=["empty", "corrupt"])
    def test_wraps_corruption(self, content) -> None:
        with pytest.raises(ImageTransformError, match="corrupt") as exc_info:
            load_normalized(content, policy=ColourProfilePolicy.PRESERVE)
        assert exc_info.value.reason

    @pytest.mark.parametrize("policy", list(ColourProfilePolicy), ids=lambda p: p.value)
    def test_icc_policy_and_alpha(self, policy) -> None:
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        with BytesIO() as buffer:
            Image.new("RGBA", (2, 2), (20, 40, 60, 77)).save(
                buffer,
                format="PNG",
                icc_profile=profile,
            )
            result = load_normalized(buffer.getvalue(), policy=policy)
        assert result.pixels.getpixel((0, 0)) == (20, 40, 60, 77)
        assert result.icc_profile == (profile if policy is ColourProfilePolicy.PRESERVE else None)

    def test_converts_profile_pixels(self) -> None:
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB")).tobytes()
        image = Image.new("LAB", (2, 2), (128, 128, 128))
        with BytesIO() as buffer:
            image.save(buffer, format="TIFF", icc_profile=profile)
            result = load_normalized(
                buffer.getvalue(),
                policy=ColourProfilePolicy.CONVERT_SRGB_AND_STRIP,
            )
        assert result.pixels.mode == "RGB"
        assert result.pixels.getpixel((0, 0)) != (128, 128, 128)
        assert result.icc_profile is None

    def test_invalid_profile_is_not_silently_stripped(self) -> None:
        with BytesIO() as buffer:
            Image.new("RGB", (2, 2)).save(buffer, format="PNG", icc_profile=b"invalid")
            with pytest.raises(ImageTransformError, match="colour"):
                load_normalized(
                    buffer.getvalue(),
                    policy=ColourProfilePolicy.CONVERT_SRGB_AND_STRIP,
                )


class TestResizePixels:
    @pytest.mark.parametrize("size", [(1000, 1), (1, 1000)], ids=["wide", "tall"])
    def test_fit_retains_at_least_one_pixel(self, size) -> None:
        source = DecodedImage(
            pixels=Image.new("RGB", size),
            source_format="PNG",
            original_width=size[0],
            original_height=size[1],
            icc_profile=None,
        )
        assert resize_pixels(source, operation=ResizeOperation.FIT, width=1, height=1).size == (
            1,
            1,
        )

    @pytest.mark.parametrize(
        ("operation", "width", "height", "expected"),
        [
            (ResizeOperation.FIT, 30, 30, (30, 15)),
            (ResizeOperation.COVER, 30, 30, (30, 30)),
            (ResizeOperation.WIDTH, 20, None, (20, 10)),
            (ResizeOperation.HEIGHT, None, 10, (20, 10)),
        ],
        ids=["fit", "cover", "width", "height"],
    )
    def test_dimensions(self, source, operation, width, height, expected) -> None:
        result = resize_pixels(source, operation=operation, width=width, height=height)
        assert result.size == expected
        assert source.pixels.size == (80, 40)

    def test_centered_cover(self, source) -> None:
        source.pixels.paste("blue", (20, 0, 60, 40))
        result = resize_pixels(source, operation=ResizeOperation.COVER, width=40, height=40)
        assert result.tobytes() == Image.new("RGB", (40, 40), "blue").tobytes()

    @pytest.mark.parametrize("width", [None, 0, -1], ids=["missing", "zero", "negative"])
    def test_rejects_invalid_dimension(self, source, width) -> None:
        with pytest.raises(ImageTransformError, match="dimension"):
            resize_pixels(source, operation=ResizeOperation.WIDTH, width=width)


class TestEncodeClean:
    @pytest.mark.parametrize(
        "fmt",
        [f for f in ("PNG", "JPEG", "WEBP", "AVIF") if can_encode_format(f)],
        ids=str.lower,
    )
    def test_round_trip_and_metadata(self, source, fmt) -> None:
        source.pixels.getexif()[315] = "private author"
        source.pixels.info.update(
            exif=source.pixels.getexif().tobytes(),
            xmp=b"private",
            icc_profile=b"private",
        )
        content = encode_clean(source.pixels, output_format=fmt, quality=80, icc_profile=None)
        with Image.open(BytesIO(content)) as result:
            result.load()
            assert result.size == (80, 40)
            assert result.format == fmt
            assert not result.getexif()
            assert "xmp" not in result.info
            assert "icc_profile" not in result.info
        assert source.pixels.info["xmp"] == b"private"

    def test_explicit_icc_is_preserved(self, source) -> None:
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        content = encode_clean(
            source.pixels, output_format="PNG", quality=None, icc_profile=profile
        )
        with Image.open(BytesIO(content)) as image:
            assert image.info["icc_profile"] == profile

    def test_rejects_unknown_encoder(self, source) -> None:
        with pytest.raises(ImageTransformError, match="encoder"):
            encode_clean(source.pixels, output_format="UNKNOWN", quality=None, icc_profile=None)
