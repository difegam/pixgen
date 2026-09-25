"""Map decoded image formats to MIME types."""

from __future__ import annotations

__all__: list[str] = [
    "FORMAT_TO_MIME",
    "SUPPORTED_FORMATS",
    "format_to_mime",
]

FORMAT_TO_MIME: dict[str, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

SUPPORTED_FORMATS: frozenset[str] = frozenset(FORMAT_TO_MIME.keys())


def format_to_mime(fmt: str) -> str:
    """Convert a decoded format name to a MIME type."""
    try:
        return FORMAT_TO_MIME[fmt]
    except KeyError:
        raise ValueError(f"unsupported image format: {fmt}") from None
