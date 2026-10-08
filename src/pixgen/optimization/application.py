"""Execute local optimisation plans and publish verified variants atomically."""

import uuid
from contextlib import closing
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image, UnidentifiedImageError

from pixgen.artifacts import write_atomic
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.results import OptimizeResult, OptimizeVariantResult, PublicError, VariantStatus
from pixgen.images.transform import (
    ColourProfilePolicy,
    ImageTransformError,
    encode_clean,
    load_normalized,
    resize_pixels,
)
from pixgen.optimization.planner import build_plan

if TYPE_CHECKING:
    from pixgen.config.models import Settings
    from pixgen.images.transform import DecodedImage
    from pixgen.optimization.models import OptimizePlan, OptimizeRequest, PlannedVariant

__all__: list[str] = ["OptimizeApplication"]


def _planned_result(plan: OptimizePlan, variant: PlannedVariant) -> OptimizeVariantResult:
    """Expose a runnable planned variant or a no-upscale skip."""
    if variant.reason is not None:
        return OptimizeVariantResult(
            name=variant.spec.name, status=VariantStatus.SKIPPED, reason=variant.reason
        )
    return OptimizeVariantResult(
        name=variant.spec.name,
        status=VariantStatus.PLANNED,
        output_path=variant.output_path,
        format=plan.format,
        width=variant.width,
        height=variant.height,
    )


def _prepare_directories(plan: OptimizePlan, *, configured: bool) -> None:
    """Create runnable output parents only when execution policy permits."""
    explicit = plan.request.output is not None or plan.request.output_dir is not None or configured
    for directory in dict.fromkeys(variant.output_path.parent for variant in plan.runnable):
        if not directory.exists() and explicit and not plan.request.mkdir:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"output directory does not exist: {directory} (use --mkdir to create)",
            )
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST, f"cannot create output directory: {directory}"
            ) from exc


def _verify_output(data: bytes, plan: OptimizePlan, variant: PlannedVariant) -> None:
    """Check encoded structure and decode pixels before allowing publication."""
    try:
        with BytesIO(data) as buffer, Image.open(buffer) as image:
            image.verify()
        with BytesIO(data) as buffer, Image.open(buffer) as image:
            image.load()
            if image.format != plan.format or image.size != (variant.width, variant.height):
                raise ImageTransformError("encoded output format or dimensions differ from plan")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, ImageTransformError):
            raise
        raise ImageTransformError("encoded output is unrecognised or corrupt") from exc


def _execute_variant(
    plan: OptimizePlan, variant: PlannedVariant, source: DecodedImage
) -> OptimizeVariantResult:
    """Transform and verify one variant before its atomic publication."""
    try:
        with closing(
            resize_pixels(
                source,
                operation=variant.spec.operation,
                width=variant.spec.width,
                height=variant.spec.height,
            )
        ) as pixels:
            data = encode_clean(
                pixels,
                output_format=plan.format,
                quality=plan.quality,
                icc_profile=source.icc_profile,
            )
        _verify_output(data, plan, variant)
    except (ImageTransformError, OSError, ValueError) as exc:
        return OptimizeVariantResult(
            name=variant.spec.name,
            status=VariantStatus.FAILED,
            error=PublicError(code=ErrorCode.OPTIMIZATION_FAILED, message=f"{exc}"),
        )
    try:
        write_atomic(variant.output_path, data, overwrite=plan.request.force)
    except OSError as exc:
        return OptimizeVariantResult(
            name=variant.spec.name,
            status=VariantStatus.FAILED,
            error=PublicError(code=ErrorCode.ARTIFACT_FAILURE, message=f"{exc}"),
        )
    return OptimizeVariantResult(
        name=variant.spec.name,
        status=VariantStatus.COMPLETED,
        output_path=variant.output_path,
        format=plan.format,
        width=variant.width,
        height=variant.height,
        output_bytes=len(data),
    )


class OptimizeApplication:
    """Orchestrate sequential local image optimisation without provider clients."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(self, request: OptimizeRequest) -> OptimizeResult:
        """Plan a request or execute and retain each variant's independent outcome."""
        run_id = uuid.uuid4()
        try:
            plan = build_plan(request, default_output_dir=self._settings.generation.output_dir)
            if request.dry_run or not plan.runnable:
                variants = tuple(_planned_result(plan, variant) for variant in plan.variants)
            else:
                try:
                    source = load_normalized(
                        plan.source.content, policy=ColourProfilePolicy.PRESERVE
                    )
                except ImageTransformError as exc:
                    raise PixgenError(ErrorCode.INVALID_REQUEST, exc.reason) from exc
                with closing(source.pixels):
                    _prepare_directories(
                        plan, configured=self._settings.generation.output_dir is not None
                    )
                    variants = tuple(
                        _planned_result(plan, variant)
                        if variant.reason is not None
                        else _execute_variant(plan, variant, source)
                        for variant in plan.variants
                    )
            return OptimizeResult(
                run_id=run_id,
                source_path=plan.source.source_path,
                dry_run=request.dry_run,
                variants=variants,
            )
        except PixgenError as exc:
            return OptimizeResult(
                run_id=run_id,
                source_path=request.source,
                dry_run=request.dry_run,
                error=PublicError(code=exc.code, message=exc.message),
            )
