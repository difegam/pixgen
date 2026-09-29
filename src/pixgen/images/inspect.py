"""Load and inspect local image files."""

from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image, UnidentifiedImageError

from pixgen.images.models import ImageInputError, LocalImage

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "load_image",
]

_MAX_INPUT_BYTES = 52_428_800  # 50 MiB

_FORMAT_TO_MEDIA_TYPE: dict[str, str] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


def load_image(path: Path, *, max_bytes: int = _MAX_INPUT_BYTES) -> LocalImage:
    """Load, decode-verify, and return a local image file as a LocalImage."""
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
        media_type=_identify_media_type(path, content),
    )


def _identify_media_type(path: Path, content: bytes) -> str:
    """Decode-verify image bytes and return the matching media type."""
    try:
        with Image.open(BytesIO(content)) as image:
            media_type = _FORMAT_TO_MEDIA_TYPE.get(image.format or "")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageInputError(path, "unsupported, unrecognised, or corrupt image format") from exc

    if media_type is None:
        raise ImageInputError(path, "unsupported or unrecognised image format")
    return media_type
