from enum import StrEnum
from pathlib import Path  # noqa: TC003
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from pixgen.core.utils import file_exists, file_integrity, is_supported_image_extension

# Regular expression pattern for validating model IDs
model_id_regex = r"^[a-z0-9][a-z0-9-]*/.+$"  # namespace/model-name

type ModelId = Annotated[
    str,
    StringConstraints(pattern=model_id_regex, min_length=3),
]


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class MediaRole(StrEnum):
    IMAGE = "image"
    REFERENCE = "reference"
    MASK = "mask"
    START_FRAME = "start-frame"


class Capability(StrEnum):
    TEXT_TO_IMAGE = "text-to-image"
    REFERENCE_TO_IMAGE = "reference-to-image"
    IMAGE_EDIT = "image-edit"
    TEXT_TO_VIDEO = "text-to-video"
    IMAGE_TO_VIDEO = "image-to-video"


class MediaReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: MediaRole
    path: Annotated[
        Path,
        AfterValidator(file_exists),
        AfterValidator(is_supported_image_extension),
        AfterValidator(file_integrity),
    ]
