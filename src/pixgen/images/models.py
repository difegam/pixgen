"""Define local image models, encodings and input errors."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self

from pixgen.images.mime import MIME_TO_EXTENSION

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "ImageFacts",
    "ImageFormat",
    "ImageInputError",
    "LocalImage",
]


class ImageFormat(StrEnum):
    """Name a static image encoding Pixgen can read and write."""

    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    AVIF = "avif"

    @classmethod
    def from_pillow(cls, name: str) -> Self:
        """Return the encoding for a Pillow format name such as ``JPEG``."""
        return cls(name.lower())

    @property
    def pillow_name(self) -> str:
        """Return the Pillow format name used to open and save this encoding."""
        return self.value.upper()

    @property
    def media_type(self) -> str:
        """Return the encoding's MIME type."""
        return f"image/{self.value}"

    @property
    def extension(self) -> str:
        """Return the canonical filename extension without a dot."""
        return MIME_TO_EXTENSION[self.media_type]


@dataclass(frozen=True, slots=True)
class LocalImage:
    """An immutable loaded local image."""

    source_path: Path
    filename: str
    content: bytes
    media_type: str

    @property
    def byte_size(self) -> int:
        """Return the size of the image content in bytes."""
        return len(self.content)


@dataclass(frozen=True, slots=True)
class ImageFacts:
    """Header facts about a static image, read without decoding its pixels."""

    format: ImageFormat
    width: int
    height: int
    mode: str
    has_alpha: bool
    icc_profile: bytes | None


class ImageInputError(ValueError):
    """Raised when a local image input is invalid."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")
