from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixgen.core.errors import ErrorCode
from pixgen.core.models import JsonSchema, ModelId, ModelSpec

__all__: list[str] = [
    "CommandResult",
    "ModelGetResult",
    "ModelListResult",
    "PublicError",
    "TargetResult",
]


class PublicError(BaseModel):
    """A public-facing error with a code and message."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ErrorCode = Field(description="Machine-readable error code")
    message: str = Field(min_length=1, description="Human-readable error description")


class TargetResult(BaseModel):
    """Result for a single (model, variant) target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: ModelId = Field(description="Canonical model identifier")
    variant: int = Field(ge=1, description="Variant index, starting from 1")
    artifact_path: Path | None = Field(default=None, description="Path to the written artifact")
    media_type: str | None = Field(default=None, description="Actual MIME type of the artifact")
    error: PublicError | None = Field(default=None, description="Error if generation failed")
    warnings: tuple[str, ...] = Field(default=(), description="Non-fatal warnings for this target")

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if (self.artifact_path is None) == (self.error is None):
            raise ValueError("a target result requires one artifact path or one error")
        if (self.artifact_path is None) != (self.media_type is None):
            raise ValueError("media_type accompanies an artifact path")
        return self


class CommandResult(BaseModel):
    """Public result envelope for image commands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    run_id: str = Field(min_length=1, description="Short random identifier for this run")
    results: tuple[TargetResult, ...] = Field(
        default=(), description="Per-target results in model/variant order"
    )
    error: PublicError | None = Field(
        default=None, description="Command-level error if no targets were submitted"
    )

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if bool(self.results) == (self.error is not None):
            raise ValueError("a command result requires target results or one command error")
        return self


class ModelListResult(BaseModel):
    """Public result envelope for model list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    models: tuple[ModelSpec, ...] = Field(default=(), description="Available curated models")
    error: PublicError | None = Field(default=None, description="Command-level error if any")


class ModelGetResult(BaseModel):
    """Public result envelope for model get."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    model: ModelSpec | None = Field(default=None, description="The requested model specification")
    parameter_schemas: dict[str, JsonSchema] = Field(
        default_factory=dict,
        description="Parameter schemas keyed by operation",
    )
    error: PublicError | None = Field(default=None, description="Command-level error if any")

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if (self.model is None) == (self.error is None):
            raise ValueError("a model result requires one model or one error")
        return self
