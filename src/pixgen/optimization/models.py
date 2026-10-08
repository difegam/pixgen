"""Define immutable optimisation requests and validated output plans."""

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixgen.images.models import LocalImage
from pixgen.images.transform import ResizeOperation

__all__: list[str] = [
    "OptimizePlan",
    "OptimizeRequest",
    "OutputFormat",
    "PlannedVariant",
    "ResizeSpec",
]


class OutputFormat(StrEnum):
    """Select the source encoding or an explicit output encoding."""

    KEEP = "keep"
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    AVIF = "avif"


class OptimizeRequest(BaseModel):
    """Retain raw options until planning can report domain validation errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Path = Field(description="Local source path")
    web: bool = Field(default=False, description="Expand website variants")
    fit: tuple[str, ...] = Field(default=(), description="Ordered fit bounds")
    cover: tuple[str, ...] = Field(default=(), description="Ordered cover dimensions")
    width: tuple[str | int, ...] = Field(default=(), description="Ordered target widths")
    height: tuple[str | int, ...] = Field(default=(), description="Ordered target heights")
    format: OutputFormat | str | None = Field(default=None, description="Output format override")
    quality: int | None = Field(default=None, description="Lossy encoding quality override")
    output: Path | None = Field(default=None, description="Explicit single output path")
    output_dir: Path | None = Field(default=None, description="Named output directory")
    dry_run: bool = Field(default=False, description="Report the plan without execution")
    mkdir: bool = Field(default=False, description="Permit directory creation during execution")
    force: bool = Field(default=False, description="Permit replacing existing outputs")


class ResizeSpec(BaseModel):
    """Describe one named operation with its required target dimensions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, description="Stable derived variant name")
    operation: ResizeOperation = Field(description="Resize or crop operation")
    width: int | None = Field(default=None, gt=0, description="Target width or fit bound")
    height: int | None = Field(default=None, gt=0, description="Target height or fit bound")

    @model_validator(mode="after")
    def _validate_dimensions(self) -> Self:
        """Require exactly the dimensions consumed by the selected operation."""
        required = {
            ResizeOperation.FIT: (True, True),
            ResizeOperation.COVER: (True, True),
            ResizeOperation.WIDTH: (True, False),
            ResizeOperation.HEIGHT: (False, True),
        }[self.operation]
        if (self.width is not None, self.height is not None) != required:
            raise ValueError(f"invalid dimensions for {self.operation}")
        return self


class PlannedVariant(BaseModel):
    """Retain a destination and effective dimensions or an expected skip reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: ResizeSpec = Field(description="Validated operation and effective bounds")
    output_path: Path = Field(description="Resolved absolute destination")
    width: int = Field(gt=0, description="Output width in pixels")
    height: int = Field(gt=0, description="Output height in pixels")
    reason: str | None = Field(default=None, description="No-upscale skip reason")


class OptimizePlan(BaseModel):
    """Carry validated source facts and all outputs in request order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request: OptimizeRequest = Field(description="Execution flags and original options")
    source: LocalImage = Field(description="Verified original bytes and source path")
    source_format: str = Field(description="Pillow source format")
    source_width: int = Field(gt=0, description="EXIF-oriented source width")
    source_height: int = Field(gt=0, description="EXIF-oriented source height")
    has_alpha: bool = Field(description="Source has an alpha channel or transparency metadata")
    format: str = Field(description="Resolved Pillow output format")
    quality: int | None = Field(description="Resolved encoder quality or Pillow default")
    variants: tuple[PlannedVariant, ...] = Field(description="All variants in deterministic order")

    @property
    def runnable(self) -> tuple[PlannedVariant, ...]:
        """Return runnable variants in plan order."""
        return tuple(variant for variant in self.variants if variant.reason is None)

    @property
    def skipped(self) -> tuple[PlannedVariant, ...]:
        """Return no-upscale skips in plan order."""
        return tuple(variant for variant in self.variants if variant.reason is not None)


OptimizePlan.model_rebuild(_types_namespace={"Path": Path})
