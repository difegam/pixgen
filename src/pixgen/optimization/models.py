"""Define immutable optimisation requests and validated output plans."""

from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixgen.core.results import OptimizeVariantResult, PublicError, VariantStatus
from pixgen.images.models import ImageFormat, LocalImage
from pixgen.images.transform import ResizeOperation, ResizeTarget, fit_dimensions

__all__: list[str] = [
    "OptimizePlan",
    "OptimizeRequest",
    "OutputFormat",
    "PlannedVariant",
    "ResizeSpec",
]

_UPSCALE_REASON = "would upscale"


class OutputFormat(StrEnum):
    """Select the source encoding or an explicit output encoding."""

    KEEP = "keep"
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    AVIF = "avif"

    def resolve(self, source: ImageFormat) -> ImageFormat:
        """Return the concrete encoding, substituting the source's for ``keep``."""
        return source if self is OutputFormat.KEEP else ImageFormat(self.value)


class OptimizeRequest(BaseModel):
    """Retain raw sizing options until planning can report domain validation errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Path = Field(description="Local source path")
    web: bool = Field(default=False, description="Expand website variants")
    fit: tuple[str, ...] = Field(default=(), description="Ordered fit bounds")
    cover: tuple[str, ...] = Field(default=(), description="Ordered cover dimensions")
    width: tuple[str | int, ...] = Field(default=(), description="Ordered target widths")
    height: tuple[str | int, ...] = Field(default=(), description="Ordered target heights")
    format: OutputFormat | None = Field(default=None, description="Output format override")
    quality: int | None = Field(default=None, description="Lossy encoding quality override")
    output: Path | None = Field(default=None, description="Explicit single output path")
    output_dir: Path | None = Field(default=None, description="Named output directory")
    dry_run: bool = Field(default=False, description="Report the plan without execution")
    mkdir: bool = Field(default=False, description="Permit creating an explicit output directory")
    force: bool = Field(default=False, description="Permit replacing existing outputs")


class ResizeSpec(BaseModel):
    """Describe one named operation with the target dimensions it consumes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, description="Stable derived variant name")
    operation: ResizeOperation = Field(description="Resize or crop operation")
    width: int | None = Field(default=None, gt=0, description="Target width or fit bound")
    height: int | None = Field(default=None, gt=0, description="Target height or fit bound")

    @model_validator(mode="after")
    def _validate_dimensions(self) -> Self:
        """Require exactly the dimensions consumed by the selected operation."""
        if (self.width is not None, self.height is not None) != (
            self.operation.takes_width,
            self.operation.takes_height,
        ):
            raise ValueError(f"invalid dimensions for {self.operation}")
        return self

    def resolve(self, source_width: int, source_height: int) -> ResizeTarget | None:
        """Return the output size for an oriented source, or None if it would upscale."""
        match self.operation:
            case ResizeOperation.FIT:
                bounds = (
                    min(self.width or source_width, source_width),
                    min(self.height or source_height, source_height),
                )
                width, height = fit_dimensions(source_width, source_height, bounds=bounds)
                return ResizeTarget(width=width, height=height, crop=False)
            case ResizeOperation.COVER:
                width, height = self.width or source_width, self.height or source_height
                crop = True
            case ResizeOperation.WIDTH:
                width = self.width or source_width
                height = max(1, round(Fraction(source_height * width, source_width)))
                crop = False
            case ResizeOperation.HEIGHT:
                height = self.height or source_height
                width = max(1, round(Fraction(source_width * height, source_height)))
                crop = False
            case _:
                assert_never(self.operation)
        if width > source_width or height > source_height:
            return None
        return ResizeTarget(width=width, height=height, crop=crop)


class PlannedVariant(BaseModel):
    """Retain a destination with its output size, or no size when it would upscale."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: ResizeSpec = Field(description="Validated operation and requested dimensions")
    output_path: Path = Field(description="Resolved absolute destination")
    target: ResizeTarget | None = Field(description="Output size; None skips an upscale")

    @property
    def reason(self) -> str | None:
        """Return why the variant is skipped, or None when it runs."""
        return _UPSCALE_REASON if self.target is None else None

    def planned_result(self, image_format: ImageFormat) -> OptimizeVariantResult:
        """Report the planned output, or the skip reason for an upscale."""
        if self.target is None:
            return OptimizeVariantResult(
                name=self.spec.name, status=VariantStatus.SKIPPED, reason=_UPSCALE_REASON
            )
        return self._output_result(VariantStatus.PLANNED, image_format, self.target)

    def completed_result(
        self, image_format: ImageFormat, *, output_bytes: int
    ) -> OptimizeVariantResult:
        """Report a written output and its size in bytes."""
        if self.target is None:
            raise ValueError("a skipped variant cannot complete")
        return self._output_result(
            VariantStatus.COMPLETED, image_format, self.target, output_bytes=output_bytes
        )

    def failed_result(self, error: PublicError) -> OptimizeVariantResult:
        """Report a failure for this variant."""
        return OptimizeVariantResult(name=self.spec.name, status=VariantStatus.FAILED, error=error)

    def _output_result(
        self,
        status: VariantStatus,
        image_format: ImageFormat,
        target: ResizeTarget,
        *,
        output_bytes: int | None = None,
    ) -> OptimizeVariantResult:
        """Build a planned or completed result carrying output details."""
        return OptimizeVariantResult(
            name=self.spec.name,
            status=status,
            output_path=self.output_path,
            format=image_format.pillow_name,
            width=target.width,
            height=target.height,
            output_bytes=output_bytes,
        )


class OptimizePlan(BaseModel):
    """Carry the verified source, resolved encoding and all outputs in request order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request: OptimizeRequest = Field(description="Execution flags and original options")
    source: LocalImage = Field(description="Original bytes and source path")
    format: ImageFormat = Field(description="Resolved output encoding")
    quality: int | None = Field(description="Resolved encoder quality or Pillow default")
    variants: tuple[PlannedVariant, ...] = Field(description="All variants in deterministic order")

    @property
    def runnable(self) -> tuple[PlannedVariant, ...]:
        """Return variants that will be written, in plan order."""
        return tuple(variant for variant in self.variants if variant.target is not None)

    def planned_results(self) -> tuple[OptimizeVariantResult, ...]:
        """Report every variant as planned or skipped."""
        return tuple(variant.planned_result(self.format) for variant in self.variants)


OptimizePlan.model_rebuild(_types_namespace={"Path": Path})
