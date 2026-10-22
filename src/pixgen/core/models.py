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
    TypeAdapter,
    ValidationError,
    computed_field,
    model_validator,
)

from pixgen.core.errors import ErrorCode, PixgenError

__all__: list[str] = [
    "ImageOperation",
    "JsonObject",
    "JsonSchema",
    "MediaRole",
    "MediaRoleSpec",
    "ModelId",
    "ModelSpec",
    "normalise_model_id",
]


type ModelId = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=200,
        pattern=r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*$",
    ),
]
type JsonObject = dict[str, JsonValue]
type JsonSchema = dict[str, JsonValue]


def normalise_model_id(
    value: str,
    *,
    prefix: str,
    error_message: str,
    allow_nested: bool = False,
) -> ModelId:
    """Validate and canonicalise a provider-local model name."""
    if not allow_nested:
        if value.startswith(f"{prefix}/"):
            return value
        if "/" in value:
            raise PixgenError(ErrorCode.INVALID_REQUEST, error_message)
        return f"{prefix}/{value}"

    model_id = value if value.startswith(f"{prefix}/") else f"{prefix}/{value}"
    try:
        return TypeAdapter(ModelId).validate_python(model_id)
    except ValidationError as exc:
        raise PixgenError(ErrorCode.INVALID_REQUEST, error_message) from exc


type ModelProvider = str
type ModelName = str


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

    @computed_field
    @property
    def provider(self) -> ModelProvider:
        """Return the provider part of the provider/model identifier."""
        return self.id.split("/", 1)[0]

    @computed_field
    @property
    def model(self) -> ModelName:
        """Return the model part of the provider/model identifier."""
        return self.id.split("/", 1)[1]
