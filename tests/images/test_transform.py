"""Test shared image normalisation, resizing, and clean encoding."""

from io import BytesIO

import pytest
from PIL import Image, ImageCms

from pixgen.images.inspect import has_codec
from pixgen.images.models import ImageFacts, ImageFormat
from pixgen.images.transform import (
    ImageTransformError,
    ResizeTarget,
    check_colour_profile,
    encode_clean,
    load_normalized,
    resize_pixels,
)
from tests.factories import make_cmyk_output_profile, make_cmyk_profile, make_grey_profile


def _encode(image: Image.Image, fmt: str, **options) -> bytes:
    with BytesIO() as buffer:
        image.save(buffer, format=fmt, **options)
        return buffer.getvalue()


def _profile_space(profile: bytes) -> str:
    with BytesIO(profile) as buffer:
        return ImageCms.ImageCmsProfile(buffer).profile.xcolor_space.strip()


def _facts(mode: str, profile: bytes | None) -> ImageFacts:
    return ImageFacts(
        format=ImageFormat.JPEG, width=2, height=2, mode=mode, has_alpha=False, icc_profile=profile
    )


_SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
_ENCODABLE = [f for f in ImageFormat if has_codec(f, encode=True)]


@pytest.fixture
def pixels() -> Image.Image:
    return load_normalized(
        _encode(Image.new("RGB", (80, 40), "red"), "PNG"), output_format=ImageFormat.PNG
    ).pixels


class TestLoadNormalized:
    def test_retains_transparency_from_png_colour_key(self) -> None:
        content = _encode(Image.new("RGB", (2, 2), "red"), "PNG", transparency=(255, 0, 0))
        result = load_normalized(content, output_format=ImageFormat.PNG)
        assert result.pixels.mode == "RGBA"
        assert result.pixels.getpixel((0, 0)) == (255, 0, 0, 0)

    @pytest.mark.parametrize("transparent", [False, True], ids=["opaque", "colour-key"])
    def test_palette_becomes_rgb_or_rgba(self, transparent) -> None:
        options = {"transparency": 0} if transparent else {}
        content = _encode(Image.new("P", (2, 2)), "PNG", **options)
        result = load_normalized(content, output_format=ImageFormat.WEBP)
        assert result.pixels.mode == ("RGBA" if transparent else "RGB")

    def test_applies_orientation_and_clears_metadata(self) -> None:
        exif = Image.Exif()
        exif[274] = 6
        content = _encode(Image.new("RGB", (30, 20), "red"), "JPEG", exif=exif)
        result = load_normalized(content, output_format=ImageFormat.JPEG)
        assert result.pixels.size == (20, 30)
        assert result.pixels.getexif().get(274) is None
        assert not result.pixels.info

    @pytest.mark.parametrize("content", [b"", b"not an image"], ids=["empty", "corrupt"])
    def test_wraps_corruption(self, content) -> None:
        with pytest.raises(ImageTransformError, match="corrupt") as exc_info:
            load_normalized(content, output_format=ImageFormat.PNG)
        assert exc_info.value.reason

    @pytest.mark.parametrize(
        "output_format", [f for f in _ENCODABLE if f is not ImageFormat.JPEG], ids=str
    )
    def test_keeps_matching_rgb_profile_and_alpha(self, output_format) -> None:
        content = _encode(Image.new("RGBA", (2, 2), (20, 40, 60, 77)), "PNG", icc_profile=_SRGB)
        result = load_normalized(content, output_format=output_format)
        assert result.pixels.getpixel((0, 0)) == (20, 40, 60, 77)
        assert result.icc_profile == _SRGB

    def test_drops_mismatched_profile(self) -> None:
        content = _encode(Image.new("RGB", (2, 2)), "PNG", icc_profile=make_cmyk_profile())
        assert load_normalized(content, output_format=ImageFormat.PNG).icc_profile is None

    @pytest.mark.parametrize(
        ("output_format", "kept"),
        [(ImageFormat.PNG, True), (ImageFormat.JPEG, True), (ImageFormat.WEBP, False)],
        ids=["png", "jpeg", "webp-stores-rgb"],
    )
    def test_grey_profile_kept_only_where_encoder_stores_grey(self, output_format, kept) -> None:
        profile = make_grey_profile()
        content = _encode(Image.new("L", (2, 2), 128), "PNG", icc_profile=profile)
        result = load_normalized(content, output_format=output_format)
        assert result.pixels.mode == "L"
        assert result.icc_profile == (profile if kept else None)


class TestModeConversion:
    @pytest.mark.parametrize(
        "output_format",
        [f for f in _ENCODABLE if f is not ImageFormat.JPEG],
        ids=str,
    )
    def test_cmyk_with_profile_is_colour_managed_to_srgb(self, output_format) -> None:
        cyan = (255, 0, 0, 0)
        content = _encode(
            Image.new("CMYK", (2, 2), cyan), "JPEG", icc_profile=make_cmyk_output_profile()
        )
        result = load_normalized(content, output_format=output_format)
        red, green, blue = result.pixels.getpixel((0, 0))
        assert result.pixels.mode == "RGB"
        assert max(red, green, blue) - min(red, green, blue) <= 2
        assert 100 < red < 230
        assert result.icc_profile is not None
        assert _profile_space(result.icc_profile) == "RGB"

    def test_cmyk_without_profile_is_converted_plainly(self) -> None:
        content = _encode(Image.new("CMYK", (2, 2)), "JPEG")
        result = load_normalized(content, output_format=ImageFormat.PNG)
        assert (result.pixels.mode, result.icc_profile) == ("RGB", None)

    def test_cmyk_stays_cmyk_for_jpeg(self) -> None:
        profile = make_cmyk_profile()
        content = _encode(Image.new("CMYK", (2, 2)), "JPEG", icc_profile=profile)
        result = load_normalized(content, output_format=ImageFormat.JPEG)
        assert (result.pixels.mode, result.icc_profile) == ("CMYK", profile)

    def test_unconvertible_cmyk_profile_fails(self) -> None:
        content = _encode(Image.new("CMYK", (2, 2)), "JPEG", icc_profile=make_cmyk_profile())
        with pytest.raises(ImageTransformError, match="sRGB"):
            load_normalized(content, output_format=ImageFormat.PNG)

    def test_sixteen_bit_grey_is_kept_for_png(self) -> None:
        image = Image.new("I;16", (1, 1), 1000)
        result = load_normalized(_encode(image, "PNG"), output_format=ImageFormat.PNG)
        assert result.pixels.mode == "I;16"
        assert result.pixels.getpixel((0, 0)) == 1000

    @pytest.mark.parametrize(
        "output_format",
        [f for f in _ENCODABLE if f is not ImageFormat.PNG],
        ids=str,
    )
    def test_sixteen_bit_grey_is_scaled_not_clipped(self, output_format) -> None:
        image = Image.new("I;16", (3, 1))
        for x, value in enumerate((1000, 65535, 0)):
            image.putpixel((x, 0), value)
        result = load_normalized(_encode(image, "PNG"), output_format=output_format)
        assert result.pixels.mode == "L"
        assert [result.pixels.getpixel((x, 0)) for x in range(3)] == [3, 255, 0]

    def test_bilevel_becomes_grey(self) -> None:
        result = load_normalized(
            _encode(Image.new("1", (2, 2)), "PNG"), output_format=ImageFormat.PNG
        )
        assert result.pixels.mode == "L"


class TestCheckColourProfile:
    def test_accepts_missing_and_readable_profiles(self) -> None:
        check_colour_profile(_facts("RGB", None), output_format=ImageFormat.WEBP)
        check_colour_profile(_facts("RGB", _SRGB), output_format=ImageFormat.WEBP)
        check_colour_profile(
            _facts("CMYK", make_cmyk_output_profile()), output_format=ImageFormat.WEBP
        )

    def test_rejects_unreadable_profile(self) -> None:
        with pytest.raises(ImageTransformError, match="colour profile"):
            check_colour_profile(_facts("RGB", b"invalid"), output_format=ImageFormat.PNG)

    def test_rejects_cmyk_profile_that_cannot_reach_srgb(self) -> None:
        with pytest.raises(ImageTransformError, match="sRGB"):
            check_colour_profile(_facts("CMYK", make_cmyk_profile()), output_format=ImageFormat.PNG)

    def test_cmyk_profile_for_jpeg_needs_no_conversion(self) -> None:
        check_colour_profile(_facts("CMYK", make_cmyk_profile()), output_format=ImageFormat.JPEG)


class TestResizePixels:
    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            (ResizeTarget(width=30, height=15, crop=False), (30, 15)),
            (ResizeTarget(width=30, height=30, crop=True), (30, 30)),
        ],
        ids=["scale", "crop"],
    )
    def test_dimensions(self, pixels, target, expected) -> None:
        assert resize_pixels(pixels, target).size == expected
        assert pixels.size == (80, 40)

    def test_centered_cover(self, pixels) -> None:
        pixels.paste("blue", (20, 0, 60, 40))
        result = resize_pixels(pixels, ResizeTarget(width=40, height=40, crop=True))
        assert result.tobytes() == Image.new("RGB", (40, 40), "blue").tobytes()


class TestEncodeClean:
    @pytest.mark.parametrize("fmt", _ENCODABLE, ids=str)
    def test_round_trip_and_metadata(self, pixels, fmt) -> None:
        pixels.getexif()[315] = "private author"
        pixels.info.update(
            exif=pixels.getexif().tobytes(),
            xmp=b"private",
            icc_profile=b"private",
        )
        content = encode_clean(pixels, output_format=fmt, quality=80, icc_profile=None)
        with Image.open(BytesIO(content)) as result:
            result.load()
            assert result.size == (80, 40)
            assert result.format == fmt.pillow_name
            assert not result.getexif()
            assert "xmp" not in result.info
            assert "icc_profile" not in result.info
        assert pixels.info["xmp"] == b"private"

    def test_explicit_icc_is_preserved(self, pixels) -> None:
        content = encode_clean(
            pixels, output_format=ImageFormat.PNG, quality=None, icc_profile=_SRGB
        )
        with Image.open(BytesIO(content)) as image:
            assert image.info["icc_profile"] == _SRGB

    def test_rejects_out_of_range_quality(self, pixels) -> None:
        with pytest.raises(ImageTransformError, match="quality"):
            encode_clean(pixels, output_format=ImageFormat.WEBP, quality=101, icc_profile=None)
