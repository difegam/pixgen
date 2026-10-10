"""Test optimisation request, resize and plan models."""

from pathlib import Path

import pytest

from pixgen.core.errors import ErrorCode
from pixgen.core.results import PublicError, VariantStatus
from pixgen.images.models import ImageFormat
from pixgen.images.transform import ResizeOperation, ResizeTarget
from pixgen.optimization.models import OutputFormat, PlannedVariant, ResizeSpec


class TestOutputFormat:
    @pytest.mark.parametrize(
        ("selected", "expected"),
        [(OutputFormat.KEEP, ImageFormat.PNG), (OutputFormat.WEBP, ImageFormat.WEBP)],
        ids=["keep", "explicit"],
    )
    def test_resolve(self, selected, expected) -> None:
        assert selected.resolve(ImageFormat.PNG) is expected


class TestResizeSpecResolve:
    @pytest.mark.parametrize(
        ("operation", "width", "height", "expected"),
        [
            (ResizeOperation.FIT, 30, 30, ResizeTarget(width=30, height=15, crop=False)),
            (ResizeOperation.FIT, 900, 900, ResizeTarget(width=80, height=40, crop=False)),
            (ResizeOperation.COVER, 30, 30, ResizeTarget(width=30, height=30, crop=True)),
            (ResizeOperation.WIDTH, 20, None, ResizeTarget(width=20, height=10, crop=False)),
            (ResizeOperation.HEIGHT, None, 10, ResizeTarget(width=20, height=10, crop=False)),
        ],
        ids=["fit", "fit-clamped", "cover", "width", "height"],
    )
    def test_targets(self, operation, width, height, expected) -> None:
        spec = ResizeSpec(name="size", operation=operation, width=width, height=height)
        assert spec.resolve(80, 40) == expected

    @pytest.mark.parametrize(
        ("operation", "width", "height"),
        [
            (ResizeOperation.COVER, 90, 10),
            (ResizeOperation.WIDTH, 81, None),
            (ResizeOperation.HEIGHT, None, 41),
        ],
        ids=["cover", "width", "height"],
    )
    def test_upscale_resolves_to_none(self, operation, width, height) -> None:
        spec = ResizeSpec(name="size", operation=operation, width=width, height=height)
        assert spec.resolve(80, 40) is None

    def test_proportional_rounding_is_exact_for_huge_sources(self) -> None:
        spec = ResizeSpec(name="size", operation=ResizeOperation.WIDTH, width=3)
        target = spec.resolve(2 * 10**30, 10**30 + 1)
        assert target == ResizeTarget(width=3, height=2, crop=False)


class TestPlannedVariantResults:
    def _variant(self, target: ResizeTarget | None) -> PlannedVariant:
        spec = ResizeSpec(name="width-20", operation=ResizeOperation.WIDTH, width=20)
        return PlannedVariant(spec=spec, output_path=Path("/out/photo.webp"), target=target)

    def test_planned_and_completed(self) -> None:
        variant = self._variant(ResizeTarget(width=20, height=10, crop=False))
        planned = variant.planned_result(ImageFormat.WEBP)
        completed = variant.completed_result(ImageFormat.WEBP, output_bytes=42)
        assert (planned.status, planned.format, planned.width) == (
            VariantStatus.PLANNED,
            "WEBP",
            20,
        )
        assert (completed.status, completed.output_bytes) == (VariantStatus.COMPLETED, 42)

    def test_skip_and_failure(self) -> None:
        variant = self._variant(None)
        skipped = variant.planned_result(ImageFormat.WEBP)
        failed = variant.failed_result(
            PublicError(code=ErrorCode.OPTIMIZATION_FAILED, message="broken")
        )
        assert (skipped.status, skipped.reason) == (VariantStatus.SKIPPED, "would upscale")
        assert failed.status is VariantStatus.FAILED
        with pytest.raises(ValueError, match="skipped"):
            variant.completed_result(ImageFormat.WEBP, output_bytes=1)
