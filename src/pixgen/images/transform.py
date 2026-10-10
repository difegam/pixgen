"""Decode pixels into an encoder-ready mode, resize them, and encode clean local images.

Exports ``load_normalized`` for decoding, ``check_colour_profile`` for header-time
profile validation, ``resize_pixels`` and ``encode_clean``.
"""

from enum import StrEnum
from fractions import Fraction
from io import BytesIO

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from pixgen.images.models import ImageFacts, ImageFormat

__all__: list[str] = [
    "DecodedImage",
    "ImageTransformError",
    "ResizeOperation",
    "ResizeTarget",
    "check_colour_profile",
    "encode_clean",
    "fit_dimensions",
    "load_normalized",
    "resize_pixels",
]

_SIXTEEN_BIT_MODES = frozenset({"I", "I;16", "I;16B", "I;16L", "I;16N"})
_GREY_MODES = frozenset({"L", "LA"}) | _SIXTEEN_BIT_MODES
_EIGHT_BIT_SCALE = 257


class ResizeOperation(StrEnum):
    """Select proportional resize or centred cover crop behaviour."""

    FIT = "fit"
    COVER = "cover"
    WIDTH = "width"
    HEIGHT = "height"

    @property
    def takes_width(self) -> bool:
        """Return whether the operation consumes a target width."""
        return self is not ResizeOperation.HEIGHT

    @property
    def takes_height(self) -> bool:
        """Return whether the operation consumes a target height."""
        return self is not ResizeOperation.WIDTH


class ResizeTarget(BaseModel):
    """Describe final pixel dimensions and whether to centre-crop to reach them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int = Field(gt=0, description="Output width in pixels")
    height: int = Field(gt=0, description="Output height in pixels")
    crop: bool = Field(description="Centre-crop to the exact size instead of scaling")


class DecodedImage(BaseModel):
    """Carry oriented, encoder-ready pixels and the colour profile to embed."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    pixels: Image.Image = Field(description="Loaded pixels after orientation and mode conversion")
    icc_profile: bytes | None = Field(description="ICC profile matching the encoded pixels")


class ImageTransformError(ValueError):
    """Report invalid image data or a failed local transform."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"image transform failed: {reason}")


def fit_dimensions(width: int, height: int, *, bounds: tuple[int, int]) -> tuple[int, int]:
    """Calculate proportional fit dimensions with a one-pixel minimum."""
    scale = min(Fraction(bounds[0], width), Fraction(bounds[1], height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def check_colour_profile(facts: ImageFacts, *, output_format: ImageFormat) -> None:
    """Reject an unreadable source profile, or a CMYK profile that cannot reach sRGB.

    Raises:
        ImageTransformError: If the profile cannot be used for the selected output.
    """
    if facts.icc_profile is None:
        return
    profile = _read_profile(facts.icc_profile)
    if _needs_srgb_conversion(facts.mode, output_format):
        try:
            ImageCms.buildTransform(profile, _srgb_profile(), "CMYK", "RGB")
        except ImageCms.PyCMSError as exc:
            raise ImageTransformError("cannot convert source colour profile to sRGB") from exc


def load_normalized(content: bytes, *, output_format: ImageFormat) -> DecodedImage:
    """Decode static image bytes, apply orientation and convert to an encoder-ready mode.

    Raises:
        ImageTransformError: If the bytes cannot be decoded or converted.
    """
    try:
        with BytesIO(content) as buffer, Image.open(buffer) as image:
            image.load()
            pixels = ImageOps.exif_transpose(image)
            profile = image.info.get("icc_profile")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageTransformError("unrecognised or corrupt image data") from exc
    decoded = _convert_for_encoder(
        pixels, profile if isinstance(profile, bytes) and profile else None, output_format
    )
    decoded.pixels.info.clear()
    return decoded


def resize_pixels(image: Image.Image, target: ResizeTarget) -> Image.Image:
    """Scale pixels to the target size, centre-cropping first when the target asks to."""
    size = (target.width, target.height)
    if target.crop:
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    return image.resize(size, resample=Image.Resampling.LANCZOS)


def encode_clean(
    image: Image.Image,
    *,
    output_format: ImageFormat,
    quality: int | None,
    icc_profile: bytes | None,
) -> bytes:
    """Encode fresh pixels with only explicitly selected encoder metadata."""
    if quality is not None and not 0 <= quality <= 100:
        raise ImageTransformError("encoder quality must be between 0 and 100")
    try:
        with Image.new(image.mode, image.size) as clean, BytesIO() as buffer:
            clean.paste(image)
            kwargs: dict[str, int | bytes] = {}
            if quality is not None:
                kwargs["quality"] = quality
            if icc_profile is not None:
                kwargs["icc_profile"] = icc_profile
            clean.save(buffer, format=output_format.pillow_name, **kwargs)
            return buffer.getvalue()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ImageTransformError(f"cannot encode {output_format.pillow_name} image") from exc


def _convert_for_encoder(
    image: Image.Image, profile: bytes | None, output_format: ImageFormat
) -> DecodedImage:
    """Convert pixels the encoder cannot store and keep only a profile that still matches."""
    mode = image.mode
    if mode == "P" or (mode in {"L", "RGB"} and "transparency" in image.info):
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    elif mode == "1":
        image = image.convert("L")
    elif mode in _SIXTEEN_BIT_MODES:
        image = _convert_sixteen_bit(image, output_format)
    elif _needs_srgb_conversion(mode, output_format):
        return _cmyk_to_srgb(image, profile)
    elif mode not in {"L", "LA", "RGB", "RGBA", "CMYK"}:
        raise ImageTransformError(f"pixel mode {mode} is unsupported")
    return DecodedImage(
        pixels=image, icc_profile=_matching_profile(profile, image.mode, output_format)
    )


def _convert_sixteen_bit(image: Image.Image, output_format: ImageFormat) -> Image.Image:
    """Keep 16-bit greyscale for PNG and scale it to 8 bits for other encoders."""
    if output_format is ImageFormat.PNG:
        return image if image.mode == "I;16" else image.convert("I;16")
    return image.convert("I").point(lambda value: value / _EIGHT_BIT_SCALE).convert("L")


def _needs_srgb_conversion(mode: str, output_format: ImageFormat) -> bool:
    """Return whether CMYK pixels must become RGB for the selected encoder."""
    return mode == "CMYK" and output_format is not ImageFormat.JPEG


def _cmyk_to_srgb(image: Image.Image, profile: bytes | None) -> DecodedImage:
    """Colour-manage CMYK pixels into sRGB, or convert them plainly without a profile."""
    if profile is None:
        return DecodedImage(pixels=image.convert("RGB"), icc_profile=None)
    srgb = _srgb_profile()
    try:
        converted = ImageCms.profileToProfile(image, _read_profile(profile), srgb, outputMode="RGB")
    except ImageCms.PyCMSError as exc:
        raise ImageTransformError("cannot convert source colour profile to sRGB") from exc
    if converted is None:
        raise ImageTransformError("cannot convert source colour profile to sRGB")
    return DecodedImage(pixels=converted, icc_profile=srgb.tobytes())


def _matching_profile(profile: bytes | None, mode: str, output_format: ImageFormat) -> bytes | None:
    """Return the profile when its colour space matches the pixels the encoder stores."""
    if profile is None:
        return None
    stored_space = "CMYK" if mode == "CMYK" else "GRAY" if mode in _GREY_MODES else "RGB"
    if output_format is ImageFormat.WEBP or (output_format is ImageFormat.AVIF and mode == "LA"):
        stored_space = "RGB"
    try:
        colour_space = _read_profile(profile).profile.xcolor_space.strip()
    except ImageTransformError:
        return None
    return profile if colour_space == stored_space else None


def _read_profile(profile: bytes) -> ImageCms.ImageCmsProfile:
    """Parse ICC profile bytes."""
    try:
        with BytesIO(profile) as buffer:
            return ImageCms.ImageCmsProfile(buffer)
    except (ImageCms.PyCMSError, OSError, ValueError, TypeError) as exc:
        raise ImageTransformError("cannot read source colour profile") from exc


def _srgb_profile() -> ImageCms.ImageCmsProfile:
    """Build the built-in LittleCMS sRGB profile."""
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
