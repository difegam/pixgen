from typing import TYPE_CHECKING

from PIL import Image
from pydantic import (
    BaseModel,
    ConfigDict,
)

if TYPE_CHECKING:
    from pathlib import Path


class FieldError(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    reason: str


def file_exists(file_path: Path) -> Path:
    """Check if the file exists and is a file."""
    if not file_path.is_file():
        raise ValueError(f"File path does not exist or is not a file: {file_path}")
    return file_path


def file_integrity(file_path: Path) -> Path:
    """Check the integrity of the image file by attempting to open and verify it."""
    try:
        with Image.open(file_path) as img:
            img.verify()
    except (OSError, SyntaxError) as e:
        raise ValueError(f"File integrity check failed for {file_path}: {e}") from e
    return file_path
