"""Define local image model and input errors."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "ImageInputError",
    "LocalImage",
]


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


class ImageInputError(ValueError):
    """Raised when a local image input is invalid."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")
