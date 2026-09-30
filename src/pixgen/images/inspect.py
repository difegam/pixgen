"""Load and inspect local image files without Pillow."""

from typing import TYPE_CHECKING

import filetype

from pixgen.images.models import ImageInputError, LocalImage

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "load_image",
]

_MAX_INPUT_BYTES = 52_428_800  # 50 MiB

_SUPPORTED_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


def load_image(path: Path, *, max_bytes: int = _MAX_INPUT_BYTES) -> LocalImage:
    """Load a local image file and return a LocalImage."""
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

    kind = filetype.guess(content)
    if kind is None or kind.mime not in _SUPPORTED_MEDIA_TYPES:
        raise ImageInputError(path, "unsupported or unrecognised image format")

    return LocalImage(
        source_path=path,
        filename=path.name,
        content=content,
        media_type=kind.mime,
    )
