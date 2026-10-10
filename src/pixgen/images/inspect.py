"""Load and inspect local image files."""

from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image, UnidentifiedImageError, features

from pixgen.images.models import ImageFacts, ImageFormat, ImageInputError, LocalImage

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "has_codec",
    "inspect_header",
    "load_image",
]

_MAX_INPUT_BYTES = 52_428_800  # 50 MiB

_EXIF_ORIENTATION = 274
_SWAPPED_ORIENTATIONS = frozenset({5, 6, 7, 8})

_FORMAT_TO_FEATURE: dict[ImageFormat, str] = {
    ImageFormat.AVIF: "avif",
    ImageFormat.JPEG: "jpg",
    ImageFormat.PNG: "zlib",
    ImageFormat.WEBP: "webp",
}


def has_codec(image_format: ImageFormat, *, encode: bool) -> bool:
    """Return whether this Pillow build can read, or with ``encode`` write, a format."""
    Image.init()
    registry = Image.SAVE if encode else Image.OPEN
    if image_format.pillow_name not in registry:
        return False
    return features.check(_FORMAT_TO_FEATURE[image_format]) is True


def load_image(path: Path, *, max_bytes: int = _MAX_INPUT_BYTES, verify: bool = True) -> LocalImage:
    """Load a local image file as a LocalImage.

    Args:
        path: Local image path.
        max_bytes: Largest accepted file size.
        verify: Also check the whole encoded stream; otherwise read only the header.

    Returns:
        The loaded image bytes and media type.

    Raises:
        ImageInputError: If the file is missing, too large, empty, or not a supported image.
    """
    if not path.is_file():
        raise ImageInputError(path, "file does not exist or is not a regular file")

    try:
        stat = path.stat()
    except OSError as exc:
        raise ImageInputError(path, f"cannot stat file: {exc}") from exc

    if stat.st_size > max_bytes:
        raise ImageInputError(
            path,
            f"file size {stat.st_size} exceeds limit {max_bytes}",
        )

    if stat.st_size == 0:
        raise ImageInputError(path, "file is empty")

    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ImageInputError(path, f"cannot read file: {exc}") from exc

    return LocalImage(
        source_path=path,
        filename=path.name,
        content=content,
        media_type=_identify_media_type(path, content, verify=verify),
    )


def inspect_header(image: LocalImage) -> ImageFacts:
    """Read a static image's oriented size, mode, transparency and ICC profile.

    Raises:
        ImageInputError: If the header is unreadable or the image is animated.
    """
    try:
        with BytesIO(image.content) as buffer, Image.open(buffer) as opened:
            if getattr(opened, "is_animated", False) or getattr(opened, "n_frames", 1) > 1:
                raise ImageInputError(
                    image.source_path, "animated or multiframe images are unsupported"
                )
            width, height = opened.size
            if _header_exif(opened, image.content).get(_EXIF_ORIENTATION) in _SWAPPED_ORIENTATIONS:
                width, height = height, width
            bands = opened.getbands()
            profile = opened.info.get("icc_profile")
            return ImageFacts(
                format=ImageFormat.from_pillow(opened.format or ""),
                width=width,
                height=height,
                mode=opened.mode,
                has_alpha="A" in bands or "a" in bands or "transparency" in opened.info,
                icc_profile=profile if isinstance(profile, bytes) and profile else None,
            )
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, ImageInputError):
            raise
        raise ImageInputError(image.source_path, "cannot read source image header") from exc


def _header_exif(image: Image.Image, content: bytes) -> Image.Exif:
    """Read PNG EXIF chunks without invoking the plugin's pixel-loading getexif."""
    if image.format != "PNG":
        return image.getexif()
    exif = Image.Exif()
    with BytesIO(content) as buffer:
        buffer.seek(8)
        while header := buffer.read(8):
            if len(header) != 8:
                raise ValueError("truncated PNG chunk header")
            length = int.from_bytes(header[:4], "big")
            if header[4:] == b"eXIf":
                exif.load(buffer.read(length))
                return exif
            if header[4:] == b"IEND":
                break
            buffer.seek(length + 4, 1)
    return exif


def _identify_media_type(path: Path, content: bytes, *, verify: bool) -> str:
    """Identify image bytes, optionally verifying the stream, and return the media type."""
    try:
        with Image.open(BytesIO(content)) as image:
            name = image.format or ""
            if verify:
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageInputError(path, "unsupported, unrecognised, or corrupt image format") from exc

    try:
        return ImageFormat.from_pillow(name).media_type
    except ValueError as exc:
        raise ImageInputError(path, "unsupported or unrecognised image format") from exc
