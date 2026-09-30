"""Define curated model catalogue types and image operations."""

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

__all__: list[str] = [
    "ImageOperation",
    "JsonObject",
    "JsonSchema",
    "MediaRole",
    "MediaRoleSpec",
    "ModelId",
    "ModelSpec",
]

type ModelId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*$"),
]
type JsonObject = dict[str, JsonValue]
type JsonSchema = dict[str, JsonValue]


class ImageOperation(StrEnum):
    """Supported image operations."""

    IMAGE_CREATE = "image-create"
    IMAGE_EDIT = "image-edit"


class MediaRole(StrEnum):
    """Roles for media inputs."""

    REFERENCE = "reference"
    IMAGE = "image"


class MediaRoleSpec(BaseModel):
    """Specification for a media role's constraints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum: int = Field(default=0, ge=0, description="Minimum number of inputs required")
    maximum: int = Field(default=1, ge=1, description="Maximum number of inputs allowed")
    formats: frozenset[str] = Field(description="Accepted lower-case decoded image formats")
    max_bytes: int | None = Field(default=None, gt=0, description="Maximum bytes per input")

    @model_validator(mode="after")
    def _validate_cardinality(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class ModelSpec(BaseModel):
    """Specification for a curated image model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ModelId = Field(description="Canonical provider/model identifier")
    display_name: str = Field(min_length=1, description="Human-readable model name")
    operations: frozenset[ImageOperation] = Field(min_length=1, description="Supported operations")
    media: Mapping[MediaRole, MediaRoleSpec] = Field(
        description="Media role constraints for this model"
    )
    documentation_url: AnyHttpUrl = Field(description="Vendor documentation URL")
    verified_at: date = Field(description="Date the specification was verified")
