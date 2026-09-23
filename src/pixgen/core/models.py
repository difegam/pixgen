from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    StringConstraints,
)

from pixgen.core.validation import file_exists, file_integrity

type ModelId = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-z0-9][a-z0-9-]*/.+$",  # namespace/model-name
        min_length=3,
    ),
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


class Operation(StrEnum):
    IMAGE_CREATE = "image-create"
    IMAGE_EDIT = "image-edit"
    VIDEO_CREATE = "video-create"


class GenerationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: MediaRole
    path: Annotated[
        Path,
        AfterValidator(file_exists),
        AfterValidator(file_integrity),
    ]


class MediaRoleSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum: NonNegativeInt = 0
    maximum: PositiveInt = 1
    formats: frozenset[str]
    max_bytes: int | None = None


# Typed parameter metadata


class Kind(StrEnum):
    """Primitive data kinds for parameter specifications."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"


class IntegerParameterSpec(BaseModel):
    kind: Literal[Kind.INTEGER] = Kind.INTEGER
    minimum: int | None = None
    maximum: int | None = None
    default: int | None = None
    description: str = ""


class EnumParameterSpec(BaseModel):
    kind: Literal[Kind.ENUM] = Kind.ENUM
    values: tuple[str, ...]
    default: str | None = None
    description: str = ""


class StringParameterSpec(BaseModel):
    kind: Literal[Kind.STRING] = Kind.STRING
    pattern: str | None = None
    default: str | None = None
    description: str = ""


class NumberParameterSpec(BaseModel):
    kind: Literal[Kind.NUMBER] = Kind.NUMBER
    minimum: float | None = None
    maximum: float | None = None
    default: float | None = None
    description: str = ""


class BooleanParameterSpec(BaseModel):
    kind: Literal[Kind.BOOLEAN] = Kind.BOOLEAN
    default: bool | None = None
    description: str = ""


# Union type for all parameter specifications
type ParameterSpec = Annotated[
    StringParameterSpec
    | IntegerParameterSpec
    | NumberParameterSpec
    | BooleanParameterSpec
    | EnumParameterSpec,
    Field(discriminator="kind"),
]


class ModelSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ModelId
    display_name: str
    kind: MediaKind
    capabilities: frozenset[Capability]
    media: dict[MediaRole, MediaRoleSpec]
    parameters: dict[str, ParameterSpec]
    documentation_url: AnyHttpUrl
    verified_at: date
    supports_cancel: bool = False
