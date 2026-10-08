"""Normalise image pixels, resize them, and encode clean local images."""

from enum import StrEnum
from fractions import Fraction
from io import BytesIO
from typing import assert_never

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from pixgen.images.inspect import can_encode_format

__all__: list[str] = [
    "ColourProfilePolicy",
    "DecodedImage",
    "ImageTransformError",
    "ResizeOperation",
    "encode_clean",
    "fit_dimensions",
    "load_normalized",
    "resize_pixels",
    "validate_encoding",
]

_ENCODER_MODES: dict[str, frozenset[str]] = {
    "JPEG": frozenset({"1", "L", "RGB", "CMYK"}),
    "PNG": frozenset({"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16B"}),
    "WEBP": frozenset({"1", "L", "LA", "P", "RGB", "RGBA"}),
    "AVIF": frozenset({"1", "L", "LA", "P", "RGB", "RGBA"}),
}


class ColourProfilePolicy(StrEnum):
    """Select preservation or sRGB conversion of embedded colour profiles."""

    PRESERVE = "PRESERVE"
    CONVERT_SRGB_AND_STRIP = "CONVERT_SRGB_AND_STRIP"


class ResizeOperation(StrEnum):
    """Select proportional resize or centred cover crop behaviour."""

    FIT = "FIT"
    COVER = "COVER"
    WIDTH = "WIDTH"
    HEIGHT = "HEIGHT"


class DecodedImage(BaseModel):
    """Carry detached oriented pixels and their original dimensions."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    pixels: Image.Image = Field(description="Loaded pixels after EXIF orientation")
    source_format: str = Field(description="Original Pillow image format")
    original_width: int = Field(description="Original oriented width", gt=0)
    original_height: int = Field(description="Original oriented height", gt=0)
    icc_profile: bytes | None = Field(description="Preserved source ICC profile bytes")


class ImageTransformError(ValueError):
    """Report invalid image data or a failed local transform."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"image transform failed: {reason}")


def _convert_srgb(image: Image.Image, profile: bytes | None) -> Image.Image:
    """Convert source profile pixels to sRGB whilst retaining alpha."""
    output_mode = "RGBA" if image.mode in {"RGBA", "LA", "PA", "RGBa", "La"} else "RGB"
    if profile is None:
        return image.convert(output_mode)
    try:
        with BytesIO(profile) as buffer:
            source_profile = ImageCms.ImageCmsProfile(buffer)
        converted = ImageCms.profileToProfile(
            image,
            source_profile,
            ImageCms.createProfile("sRGB"),
            outputMode=output_mode,
        )
        if converted is None:
            raise ImageTransformError("cannot convert source colour profile to sRGB")
        return converted
    except (ImageCms.PyCMSError, OSError, ValueError, TypeError) as exc:
        raise ImageTransformError("cannot convert source colour profile to sRGB") from exc


def load_normalized(content: bytes, *, policy: ColourProfilePolicy) -> DecodedImage:
    """Decode static image bytes and apply orientation before exposing dimensions."""
    try:
        with BytesIO(content) as buffer, Image.open(buffer) as image:
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                raise ImageTransformError("animated or multiframe images are unsupported")
            source_format = image.format or ""
            image.load()
            pixels = ImageOps.exif_transpose(image)
            profile = image.info.get("icc_profile")
            icc_profile = profile if isinstance(profile, bytes) else None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, ImageTransformError):
            raise
        raise ImageTransformError("unrecognised or corrupt image data") from exc

    if "transparency" in pixels.info:
        pixels = pixels.convert("RGBA")
    elif pixels.mode == "P":
        pixels = pixels.convert("RGB")
    match policy:
        case ColourProfilePolicy.PRESERVE:
            pass
        case ColourProfilePolicy.CONVERT_SRGB_AND_STRIP:
            pixels = _convert_srgb(pixels, icc_profile)
            icc_profile = None
        case _:
            assert_never(policy)
    pixels.info.clear()
    return DecodedImage(
        pixels=pixels,
        source_format=source_format,
        original_width=pixels.width,
        original_height=pixels.height,
        icc_profile=icc_profile,
    )


def _positive_dimension(value: int | None) -> int:
    """Require a positive target pixel dimension."""
    if value is None or value <= 0:
        raise ImageTransformError("target dimension must be a positive integer")
    return value


def fit_dimensions(width: int, height: int, *, bounds: tuple[int, int]) -> tuple[int, int]:
    """Calculate proportional fit dimensions with a one-pixel minimum."""
    scale = min(Fraction(bounds[0], width), Fraction(bounds[1], height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def resize_pixels(
    source: DecodedImage,
    *,
    operation: ResizeOperation,
    width: int | None = None,
    height: int | None = None,
) -> Image.Image:
    """Resize oriented pixels proportionally or crop to exact centred cover bounds."""
    image = source.pixels
    match operation:
        case ResizeOperation.FIT:
            bounds = (_positive_dimension(width), _positive_dimension(height))
            size = fit_dimensions(image.width, image.height, bounds=bounds)
        case ResizeOperation.COVER:
            return ImageOps.fit(
                image,
                (_positive_dimension(width), _positive_dimension(height)),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        case ResizeOperation.WIDTH:
            target_width = _positive_dimension(width)
            size = (target_width, max(1, round(image.height * target_width / image.width)))
        case ResizeOperation.HEIGHT:
            target_height = _positive_dimension(height)
            size = (max(1, round(image.width * target_height / image.height)), target_height)
        case _:
            assert_never(operation)
    return image.resize(size, resample=Image.Resampling.LANCZOS)


def validate_encoding(mode: str, *, output_format: str, icc_profile: bytes | None) -> None:
    """Reject unsupported pixel modes and incompatible preserved colour profiles."""
    output_format = output_format.upper()
    if mode not in _ENCODER_MODES.get(output_format, ()):
        raise ImageTransformError(f"pixel mode {mode} is unsupported for {output_format} output")
    if icc_profile is None:
        return
    try:
        with BytesIO(icc_profile) as buffer:
            colour_space = ImageCms.ImageCmsProfile(buffer).profile.xcolor_space.strip()
    except (OSError, ValueError, TypeError) as exc:
        raise ImageTransformError("cannot read source colour profile") from exc
    source_space = (
        "CMYK" if mode == "CMYK" else "GRAY" if mode in {"1", "L", "LA", "I;16", "I;16B"} else "RGB"
    )
    output_space = source_space
    if output_format == "WEBP" or (output_format == "AVIF" and mode == "LA"):
        output_space = "RGB"
    if colour_space != source_space or colour_space != output_space:
        raise ImageTransformError(
            f"cannot preserve {colour_space} colour profile with {mode} pixels in {output_format}"
        )


def encode_clean(
    image: Image.Image,
    *,
    output_format: str,
    quality: int | None,
    icc_profile: bytes | None,
) -> bytes:
    """Encode fresh pixels with only explicitly selected encoder metadata."""
    output_format = output_format.upper()
    if not can_encode_format(output_format):
        raise ImageTransformError(f"encoder unavailable for {output_format}")
    validate_encoding(image.mode, output_format=output_format, icc_profile=icc_profile)
    if quality is not None and not 0 <= quality <= 100:
        raise ImageTransformError("encoder quality must be between 0 and 100")
    try:
        with Image.new(image.mode, image.size) as clean, BytesIO() as buffer:
            if image.mode == "P":
                palette = image.getpalette()
                if palette is not None:
                    clean.putpalette(palette)
            clean.paste(image)
            kwargs: dict[str, int | bytes] = {}
            if quality is not None:
                kwargs["quality"] = quality
            if icc_profile is not None:
                kwargs["icc_profile"] = icc_profile
            clean.save(buffer, format=output_format, **kwargs)
            return buffer.getvalue()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ImageTransformError(f"cannot encode {output_format} image") from exc
