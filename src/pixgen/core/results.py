"""Define immutable public result envelopes and per-output states."""

import uuid
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixgen.core.errors import ErrorCode
from pixgen.core.models import JsonSchema, ModelId, ModelSpec

__all__: list[str] = [
    "CommandResult",
    "GroupCreateResult",
    "GroupListResult",
    "GroupSummary",
    "ModelGetResult",
    "ModelListResult",
    "OptimizeResult",
    "OptimizeVariantResult",
    "OutcomeCounts",
    "PublicError",
    "TargetResult",
    "VariantStatus",
]


class PublicError(BaseModel):
    """A public-facing error with a code and message."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ErrorCode = Field(description="Machine-readable error code")
    message: str = Field(min_length=1, description="Human-readable error description")


class OutcomeCounts(BaseModel):
    """Count the outputs a command attempted and how many of them failed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    failed: int = Field(default=0, ge=0, description="Outputs that failed")
    attempted: int = Field(default=0, ge=0, description="Outputs the command tried to produce")


class VariantStatus(StrEnum):
    """Describe the outcome of a local optimisation variant."""

    PLANNED = "planned"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class OptimizeVariantResult(BaseModel):
    """Record one variant's resolved output or its skip/failure details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, description="Stable variant name")
    status: VariantStatus = Field(description="Planning or execution outcome")
    output_path: Path | None = Field(default=None, description="Resolved output path")
    format: str | None = Field(default=None, min_length=1, description="Resolved output format")
    width: int | None = Field(default=None, gt=0, description="Output width in pixels")
    height: int | None = Field(default=None, gt=0, description="Output height in pixels")
    output_bytes: int | None = Field(default=None, ge=0, description="Written output byte count")
    reason: str | None = Field(
        default=None, min_length=1, description="Reason the variant was skipped"
    )
    error: PublicError | None = Field(default=None, description="Error if optimisation failed")
    warnings: tuple[str, ...] = Field(default=(), description="Non-fatal variant warnings")

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        """Require exactly the details corresponding to the variant's status."""
        output_details = (self.output_path, self.format, self.width, self.height)
        if self.status in (VariantStatus.PLANNED, VariantStatus.COMPLETED):
            if any(value is None for value in output_details):
                raise ValueError(
                    "planned/completed variants require output path, format and dimensions"
                )
            if self.reason is not None or self.error is not None:
                raise ValueError("planned/completed variants cannot have a reason or error")
            if (self.output_bytes is not None) != (self.status is VariantStatus.COMPLETED):
                raise ValueError("only completed variants require an output byte count")
        else:
            if any(value is not None for value in (*output_details, self.output_bytes)):
                raise ValueError("skipped/failed variants cannot have output details")
            if self.status is VariantStatus.SKIPPED:
                if self.reason is None or self.error is not None:
                    raise ValueError("skipped variants require a reason and no error")
            elif self.error is None or self.reason is not None:
                raise ValueError("failed variants require an error and no reason")
        return self


class OptimizeResult(BaseModel):
    """Expose a versioned local optimisation run in supplied variant order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    run_id: uuid.UUID = Field(description="Unique identifier for this run")
    source_path: Path = Field(description="Source image path")
    dry_run: bool = Field(default=False, description="Whether this run only reports a plan")
    variants: tuple[OptimizeVariantResult, ...] = Field(
        default=(), description="Variants in plan order"
    )
    error: PublicError | None = Field(default=None, description="Command-level rejection error")

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        """Require variant results or a single command-level error."""
        if bool(self.variants) == (self.error is not None):
            raise ValueError("an optimise result requires variants or one command error")
        incompatible_status = VariantStatus.COMPLETED if self.dry_run else VariantStatus.PLANNED
        if any(variant.status is incompatible_status for variant in self.variants):
            raise ValueError("variant status is incompatible with dry_run")
        return self

    def outcome_counts(self) -> OutcomeCounts:
        """Count executed variants; planned and skipped variants were not attempted."""
        failed = sum(variant.status is VariantStatus.FAILED for variant in self.variants)
        completed = sum(variant.status is VariantStatus.COMPLETED for variant in self.variants)
        return OutcomeCounts(failed=failed, attempted=failed + completed)


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
    run_id: uuid.UUID = Field(description="Unique identifier for this run")
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

    def outcome_counts(self) -> OutcomeCounts:
        """Count targets and the targets that failed."""
        failed = sum(target.error is not None for target in self.results)
        return OutcomeCounts(failed=failed, attempted=len(self.results))


class GroupCreateResult(BaseModel):
    """Public result envelope for model-group creation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    name: str | None = Field(default=None, description="Created model group name")
    config_path: Path | None = Field(default=None, description="Written configuration path")
    error: PublicError | None = Field(default=None, description="Command-level error if any")

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        has_success = self.name is not None and self.config_path is not None
        if has_success == (self.error is not None):
            raise ValueError("a group result requires success details or one command error")
        return self

    def outcome_counts(self) -> OutcomeCounts:
        """Report no per-output attempts; the command succeeds or is rejected whole."""
        return OutcomeCounts()


class GroupSummary(BaseModel):
    """Public description of one configured model group."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="Model group name")
    description: str | None = Field(default=None, description="Model group description")
    tags: tuple[str, ...] = Field(default=(), description="Model group tags")
    models: tuple[ModelId, ...] = Field(default=(), description="Member model IDs in order")


class GroupListResult(BaseModel):
    """Public result envelope for model-group listing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    groups: tuple[GroupSummary, ...] = Field(default=(), description="Configured model groups")
    error: PublicError | None = Field(default=None, description="Command-level error if any")

    def outcome_counts(self) -> OutcomeCounts:
        """Report no per-output attempts; the command succeeds or is rejected whole."""
        return OutcomeCounts()


class ModelListResult(BaseModel):
    """Public result envelope for model list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    models: tuple[ModelSpec, ...] = Field(default=(), description="Available curated models")
    error: PublicError | None = Field(default=None, description="Command-level error if any")

    def outcome_counts(self) -> OutcomeCounts:
        """Report no per-output attempts; the command succeeds or is rejected whole."""
        return OutcomeCounts()


class ModelGetResult(BaseModel):
    """Public result envelope for model get."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    model: ModelSpec | None = Field(default=None, description="The requested model specification")
    parameter_schemas: dict[str, JsonSchema] = Field(
        default_factory=dict,
        description="Parameter schemas keyed by operation",
    )
    shared_aspect_ratios: dict[str, tuple[str, ...]] = Field(
        default_factory=dict,
        description="Canonical shared aspect ratios keyed by operation",
    )
    error: PublicError | None = Field(default=None, description="Command-level error if any")

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if (self.model is None) == (self.error is None):
            raise ValueError("a model result requires one model or one error")
        return self

    def outcome_counts(self) -> OutcomeCounts:
        """Report no per-output attempts; the command succeeds or is rejected whole."""
        return OutcomeCounts()
