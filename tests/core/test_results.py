"""Tests for core.results."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pixgen.core.errors import ErrorCode
from pixgen.core.results import (
    CommandResult,
    ModelGetResult,
    ModelListResult,
    PublicError,
    TargetResult,
)


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
