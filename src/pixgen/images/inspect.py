"""Load and inspect local image files without Pillow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pixgen.images.mime import SUPPORTED_FORMATS, format_to_mime
from pixgen.images.models import ImageInputError, LocalImage

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "load_image",
]

_MAX_INPUT_BYTES = 52_428_800  # 50 MiB

_MAGIC_BYTES: list[tuple[str, bytes]] = [
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("jpeg", b"\xff\xd8\xff"),
    ("webp", b"RIFF"),
]


def _sniff_format(data: bytes) -> str | None:
    """Detect image format from magic bytes."""
    for fmt, magic in _MAGIC_BYTES:
        if data[: len(magic)] == magic:
            if fmt == "webp" and data[8:12] != b"WEBP":
                continue
            return fmt
    return None


def load_image(path: Path, *, max_bytes: int = _MAX_INPUT_BYTES) -> LocalImage:
    """Load a local image file and return a LocalImage.

    Performs existence check, size guard, reads once, and sniffs format
    from magic bytes. Raises ImageInputError on any failure.
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

    fmt = _sniff_format(content)
    if fmt is None:
        raise ImageInputError(path, "unsupported or unrecognised image format")

    if fmt not in SUPPORTED_FORMATS:
        raise ImageInputError(path, f"format {fmt!r} is not supported")

    media_type = format_to_mime(fmt)

    return LocalImage(
        source_path=path,
        filename=path.name,
        content=content,
        media_type=media_type,
    )
