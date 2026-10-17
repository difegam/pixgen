"""Execute local optimisation plans and publish verified variants atomically."""

import logging
import uuid
from contextlib import closing
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image, UnidentifiedImageError

from pixgen.artifacts import create_directory, write_atomic
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.results import OptimizeResult, OptimizeVariantResult, PublicError
from pixgen.images.transform import (
    ImageTransformError,
    encode_clean,
    load_normalized,
    resize_pixels,
)
from pixgen.optimization.planner import build_plan

if TYPE_CHECKING:
    from pixgen.config.models import Settings
    from pixgen.images.transform import DecodedImage, ResizeTarget
    from pixgen.optimization.models import OptimizePlan, OptimizeRequest, PlannedVariant

__all__: list[str] = ["OptimizeApplication"]

logger = logging.getLogger(__name__)


def _public_error(code: ErrorCode, exc: Exception) -> PublicError:
    """Expose a per-variant failure with its exception message."""
    return PublicError(code=code, message=f"{exc}")


def _verify_output(data: bytes, plan: OptimizePlan, target: ResizeTarget) -> None:
    """Check encoded structure and decode pixels before allowing publication."""
    try:
        with BytesIO(data) as buffer, Image.open(buffer) as image:
            image.verify()
        with BytesIO(data) as buffer, Image.open(buffer) as image:
            image.load()
            if image.format != plan.format.pillow_name or image.size != (
                target.width,
                target.height,
            ):
                raise ImageTransformError("encoded output format or dimensions differ from plan")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, ImageTransformError):
            raise
        raise ImageTransformError("encoded output is unrecognised or corrupt") from exc


def _execute_variant(
    plan: OptimizePlan, variant: PlannedVariant, source: DecodedImage
) -> OptimizeVariantResult:
    """Transform and verify one variant before its atomic publication."""
    if variant.target is None:
        return variant.planned_result(plan.format)
    try:
        with closing(resize_pixels(source.pixels, variant.target)) as pixels:
            data = encode_clean(
                pixels,
                output_format=plan.format,
                quality=plan.quality,
                icc_profile=source.icc_profile,
            )
        _verify_output(data, plan, variant.target)
    except (ImageTransformError, OSError, ValueError) as exc:
        logger.info("optimize %s failed: %r", variant.output_path.name, exc)
        return variant.failed_result(_public_error(ErrorCode.OPTIMIZATION_FAILED, exc))
    try:
        write_atomic(variant.output_path, data, overwrite=plan.request.force)
    except OSError as exc:
        logger.info("could not write %s: %r", variant.output_path.name, exc)
        return variant.failed_result(_public_error(ErrorCode.ARTIFACT_FAILURE, exc))
    return variant.completed_result(plan.format, output_bytes=len(data))


def _execute(plan: OptimizePlan) -> tuple[OptimizeVariantResult, ...]:
    """Decode the source once, then write each runnable variant independently."""
    try:
        source = load_normalized(plan.source.content, output_format=plan.format)
    except ImageTransformError as exc:
        logger.info("could not decode source image: %s", exc.reason)
        error = PublicError(code=ErrorCode.OPTIMIZATION_FAILED, message=exc.reason)
        return tuple(
            variant.failed_result(error)
            if variant.target is not None
            else variant.planned_result(plan.format)
            for variant in plan.variants
        )
    with closing(source.pixels):
        for directory in dict.fromkeys(variant.output_path.parent for variant in plan.runnable):
            create_directory(directory, label="output directory")
        return tuple(_execute_variant(plan, variant, source) for variant in plan.variants)


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
                variants = plan.planned_results()
            else:
                variants = _execute(plan)
            return OptimizeResult(
                run_id=run_id,
                source_path=plan.source.source_path,
                dry_run=request.dry_run,
                variants=variants,
            )
        except PixgenError as exc:
            logger.info("optimize rejected: %s", exc.code)
            return OptimizeResult(
                run_id=run_id,
                source_path=request.source,
                dry_run=request.dry_run,
                error=PublicError(code=exc.code, message=exc.message),
            )
