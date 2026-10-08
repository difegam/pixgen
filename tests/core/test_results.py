"""Tests for core.results."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pixgen.core.errors import ErrorCode
from pixgen.core.results import (
    CommandResult,
    ModelGetResult,
    ModelListResult,
    OptimizeResult,
    OptimizeVariantResult,
    PublicError,
    TargetResult,
    VariantStatus,
)


class TestOptimizeVariantResult:
    """Enforce mutually exclusive optimisation result states."""

    @pytest.mark.parametrize(
        "status", [VariantStatus.PLANNED, VariantStatus.COMPLETED], ids=["planned", "completed"]
    )
    def test_output_metadata_required(self, status) -> None:
        fields = {
            "name": "card",
            "status": status,
            "output_path": Path("card.webp"),
            "format": "webp",
            "width": 1200,
            "height": 630,
        }
        if status is VariantStatus.COMPLETED:
            fields["output_bytes"] = 42
        result = OptimizeVariantResult.model_validate(fields)
        assert result.status is status
        assert result.output_bytes == (42 if status is VariantStatus.COMPLETED else None)
        for field in fields.keys() - {"name", "status"}:
            with pytest.raises(ValidationError):
                OptimizeVariantResult.model_validate(
                    {key: value for key, value in fields.items() if key != field}
                )

    @pytest.mark.parametrize(
        ("status", "details"),
        [
            (VariantStatus.SKIPPED, {"reason": "would upscale"}),
            (
                VariantStatus.FAILED,
                {"error": PublicError(code=ErrorCode.OPTIMIZATION_FAILED, message="encode failed")},
            ),
        ],
        ids=["skipped", "failed"],
    )
    def test_non_output_states_require_details(self, status, details) -> None:
        result = OptimizeVariantResult.model_validate({"name": "hero", "status": status, **details})
        assert result.output_path is None
        with pytest.raises(ValidationError):
            OptimizeVariantResult(name="hero", status=status)

    @pytest.mark.parametrize(
        ("status", "details", "extra"),
        [
            (
                "planned",
                {"output_path": "card.webp", "format": "webp", "width": 12, "height": 6},
                {"output_bytes": 42},
            ),
            (
                "planned",
                {"output_path": "card.webp", "format": "webp", "width": 12, "height": 6},
                {"reason": "would upscale"},
            ),
            (
                "completed",
                {
                    "output_path": "card.webp",
                    "format": "webp",
                    "width": 12,
                    "height": 6,
                    "output_bytes": 42,
                },
                {"error": {"code": "timeout", "message": "x"}},
            ),
            ("skipped", {"reason": "would upscale"}, {"output_path": "hero.webp"}),
            ("skipped", {"reason": "would upscale"}, {"width": 12}),
            (
                "skipped",
                {"reason": "would upscale"},
                {"error": {"code": "timeout", "message": "x"}},
            ),
            (
                "failed",
                {"error": {"code": "timeout", "message": "x"}},
                {"output_path": "hero.webp"},
            ),
            ("failed", {"error": {"code": "timeout", "message": "x"}}, {"format": "webp"}),
            ("failed", {"error": {"code": "timeout", "message": "x"}}, {"reason": "would upscale"}),
        ],
        ids=[
            "planned-bytes",
            "planned-reason",
            "completed-error",
            "skipped-path",
            "skipped-width",
            "skipped-error",
            "failed-path",
            "failed-format",
            "failed-reason",
        ],
    )
    def test_rejects_fields_from_other_states(self, status, details, extra) -> None:
        with pytest.raises(ValidationError):
            OptimizeVariantResult.model_validate(
                {"name": "card", "status": status, **details, **extra}
            )

    def test_frozen_and_forbids_extra_fields(self) -> None:
        result = OptimizeVariantResult(name="hero", status="skipped", reason="would upscale")
        with pytest.raises(ValidationError):
            result.name = "other"
        with pytest.raises(ValidationError):
            OptimizeVariantResult.model_validate({**result.model_dump(), "unknown": True})


class TestOptimizeResult:
    """Validate the versioned optimisation envelope and preserve variant order."""

    def test_ordered_variants_and_json_schema(self) -> None:
        variants = tuple(
            OptimizeVariantResult(name=name, status="skipped", reason="would upscale")
            for name in ("hero", "card")
        )
        result = OptimizeResult(
            run_id="01a0e4be-5fc8-77e9-b949-88fdc04034d7",
            source_path="source.png",
            dry_run=True,
            variants=variants,
        )
        assert result.schema_version == "1"
        assert result.variants == variants
        assert result.source_path == Path("source.png")
        assert result.dry_run is True
        assert OptimizeResult.model_validate_json(result.model_dump_json()) == result
        with pytest.raises(ValidationError):
            result.dry_run = False
        with pytest.raises(ValidationError):
            OptimizeResult.model_validate({**result.model_dump(), "unknown": True})

    @pytest.mark.parametrize("has_variants", [False, True], ids=["neither", "both"])
    def test_requires_variants_or_command_error(self, has_variants) -> None:
        fields = {"run_id": "01a0e4be-5fc8-77e9-b949-88fdc04034d7", "source_path": "source.png"}
        if has_variants:
            fields.update(
                variants=[{"name": "card", "status": "skipped", "reason": "upscale"}],
                error={"code": "invalid_request", "message": "bad input"},
            )
        with pytest.raises(ValidationError):
            OptimizeResult.model_validate(fields)

    def test_command_error_without_variants(self) -> None:
        result = OptimizeResult(
            run_id="01a0e4be-5fc8-77e9-b949-88fdc04034d7",
            source_path="source.png",
            error=PublicError(code=ErrorCode.INVALID_REQUEST, message="bad input"),
        )
        assert result.variants == ()
        assert result.error is not None


class TestPublicError:
    """Tests for PublicError."""

    def test_valid_error(self) -> None:
        error = PublicError(code=ErrorCode.TIMEOUT, message="request timed out")
        assert error.code == ErrorCode.TIMEOUT
        assert error.message == "request timed out"

    def test_empty_message_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PublicError(code=ErrorCode.TIMEOUT, message="")


class TestTargetResult:
    """Tests for TargetResult."""

    def test_success_with_artifact(self) -> None:
        result = TargetResult(
            model="openai/gpt-image-2",
            variant=1,
            artifact_path=Path("/tmp/output.png"),  # noqa: S108
            media_type="image/png",
        )
        assert result.artifact_path == Path("/tmp/output.png")  # noqa: S108
        assert result.media_type == "image/png"
        assert result.error is None

    def test_failure_with_error(self) -> None:
        result = TargetResult(
            model="openai/gpt-image-2",
            variant=1,
            error=PublicError(code=ErrorCode.TIMEOUT, message="timed out"),
        )
        assert result.artifact_path is None
        assert result.media_type is None
        assert result.error is not None

    def test_neither_artifact_nor_error_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires one artifact path or one error"):
            TargetResult(model="openai/gpt-image-2", variant=1)

    def test_both_artifact_and_error_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires one artifact path or one error"):
            TargetResult(
                model="openai/gpt-image-2",
                variant=1,
                artifact_path=Path("/tmp/x.png"),  # noqa: S108
                media_type="image/png",
                error=PublicError(code=ErrorCode.TIMEOUT, message="x"),
            )

    def test_media_type_without_artifact_rejected(self) -> None:
        with pytest.raises(ValidationError, match="media_type accompanies"):
            TargetResult(
                model="openai/gpt-image-2",
                variant=1,
                media_type="image/png",
                error=PublicError(code=ErrorCode.TIMEOUT, message="x"),
            )

    def test_warnings_allowed(self) -> None:
        result = TargetResult(
            model="openai/gpt-image-2",
            variant=1,
            artifact_path=Path("/tmp/x.png"),  # noqa: S108
            media_type="image/png",
            warnings=("suffix mismatch",),
        )
        assert result.warnings == ("suffix mismatch",)


class TestCommandResult:
    """Tests for CommandResult."""

    def test_success_with_results(self) -> None:
        target = TargetResult(
            model="openai/gpt-image-2",
            variant=1,
            artifact_path=Path("/tmp/x.png"),  # noqa: S108
            media_type="image/png",
        )
        result = CommandResult(run_id="01a0e4be-5fc8-77e9-b949-88fdc04034d7", results=(target,))
        assert result.schema_version == "1"
        assert len(result.results) == 1
        assert result.error is None

    def test_failure_with_error(self) -> None:
        result = CommandResult(
            run_id="01a0e4be-5fc8-77e9-b949-88fdc04034d7",
            error=PublicError(code=ErrorCode.INVALID_REQUEST, message="bad input"),
        )
        assert result.results == ()
        assert result.error is not None

    def test_neither_results_nor_error_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires target results or one command error"):
            CommandResult(run_id="01a0e4be-5fc8-77e9-b949-88fdc04034d7")

    def test_both_results_and_error_rejected(self) -> None:
        target = TargetResult(
            model="openai/gpt-image-2",
            variant=1,
            artifact_path=Path("/tmp/x.png"),  # noqa: S108
            media_type="image/png",
        )
        with pytest.raises(ValidationError, match="requires target results or one command error"):
            CommandResult(
                run_id="01a0e4be-5fc8-77e9-b949-88fdc04034d7",
                results=(target,),
                error=PublicError(code=ErrorCode.INVALID_REQUEST, message="x"),
            )


class TestModelListResult:
    """Tests for ModelListResult."""

    def test_empty_list(self) -> None:
        result = ModelListResult()
        assert result.schema_version == "1"
        assert result.models == ()
        assert result.error is None

    def test_with_error(self) -> None:
        result = ModelListResult(
            error=PublicError(code=ErrorCode.INVALID_CONFIGURATION, message="bad config")
        )
        assert result.models == ()
        assert result.error is not None


class TestModelGetResult:
    """Tests for ModelGetResult."""

    def test_success_with_model(self, model_spec) -> None:
        result = ModelGetResult(model=model_spec, parameter_schemas={"image-create": {}})
        assert result.model is not None
        assert result.error is None

    def test_failure_with_error(self) -> None:
        result = ModelGetResult(
            error=PublicError(code=ErrorCode.MODEL_NOT_FOUND, message="not found")
        )
        assert result.model is None
        assert result.error is not None

    def test_neither_model_nor_error_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires one model or one error"):
            ModelGetResult()

    def test_both_model_and_error_rejected(self, model_spec) -> None:
        with pytest.raises(ValidationError, match="requires one model or one error"):
            ModelGetResult(
                model=model_spec,
                error=PublicError(code=ErrorCode.MODEL_NOT_FOUND, message="x"),
            )
