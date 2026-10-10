"""Tests for CLI outcomes and exit statuses."""

import json
import uuid

import pytest
from pydantic import BaseModel, Field

from pixgen.cli.outcome import (
    CliOutcome,
    ExitStatus,
    cli_command,
    exit_status,
    failure_outcome,
    render_outcome,
)
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.results import (
    CommandResult,
    ModelGetResult,
    ModelListResult,
    OptimizeResult,
    OptimizeVariantResult,
    PublicError,
    TargetResult,
)

_RUN_ID = uuid.UUID("019cb94c-af33-7e3a-80c1-03d0294010b8")
_ERROR = PublicError(code=ErrorCode.INVALID_REQUEST, message="bad request")


def _success(variant: int = 1) -> TargetResult:
    return TargetResult(
        model="fake/model", variant=variant, artifact_path="out.png", media_type="image/png"
    )


def _failure(variant: int = 1) -> TargetResult:
    return TargetResult(model="fake/model", variant=variant, error=_ERROR)


class TestExitStatus:
    """One mapping from public results to process exit statuses."""

    @pytest.mark.parametrize(
        ("result", "expected"),
        [
            pytest.param(
                CommandResult(run_id=_RUN_ID, results=(_success(),)),
                ExitStatus.SUCCESS,
                id="all-succeeded",
            ),
            pytest.param(
                CommandResult(run_id=_RUN_ID, results=(_success(1), _failure(2))),
                ExitStatus.PARTIAL_FAILURE,
                id="some-failed",
            ),
            pytest.param(
                CommandResult(run_id=_RUN_ID, results=(_failure(1), _failure(2))),
                ExitStatus.ALL_FAILED,
                id="all-failed",
            ),
            pytest.param(
                CommandResult(run_id=_RUN_ID, error=_ERROR), ExitStatus.REJECTED, id="rejected"
            ),
            pytest.param(ModelListResult(), ExitStatus.SUCCESS, id="model-list"),
            pytest.param(ModelGetResult(error=_ERROR), ExitStatus.REJECTED, id="model-get-error"),
        ],
    )
    def test_maps_result_to_status(self, result, expected: ExitStatus) -> None:
        assert exit_status(result) is expected

    def test_outcome_reports_returncode_to_cyclopts(self) -> None:
        outcome = CliOutcome(CommandResult(run_id=_RUN_ID, error=_ERROR), as_json=False)
        assert outcome.__cyclopts_returncode__() == 2


class TestOptimizeOutcome:
    """Count completed/failed variants while ignoring expected skips."""

    @pytest.mark.parametrize(
        ("statuses", "dry_run", "expected"),
        [
            (("planned", "skipped"), True, 0),
            (("completed",), False, 0),
            (("skipped",), False, 0),
            (("failed",), False, 3),
            (("failed", "skipped"), False, 3),
            (("completed", "failed"), False, 4),
            (("skipped", "completed", "failed"), False, 4),
        ],
        ids=[
            "dry-run",
            "completed",
            "skip-only",
            "all-failed",
            "failed-and-skipped",
            "partial-failure",
            "partial-with-skip",
        ],
    )
    def test_exit_mapping(self, statuses, dry_run, expected) -> None:
        variants = []
        for index, status in enumerate(statuses):
            details = {}
            if status in ("planned", "completed"):
                details.update(output_path="out.webp", format="webp", width=12, height=6)
                if status == "completed":
                    details["output_bytes"] = 42
            elif status == "skipped":
                details["reason"] = "would upscale"
            else:
                details["error"] = _ERROR
            variants.append(
                OptimizeVariantResult.model_validate(
                    {"name": f"variant-{index}", "status": status, **details}
                )
            )
        result = OptimizeResult(
            run_id=_RUN_ID, source_path="source.png", dry_run=dry_run, variants=tuple(variants)
        )
        assert exit_status(result) == expected
        assert CliOutcome(result, as_json=False).__cyclopts_returncode__() == expected

    def test_command_error_is_rejected(self) -> None:
        result = OptimizeResult(run_id=_RUN_ID, source_path="missing.png", error=_ERROR)
        assert exit_status(result) is ExitStatus.REJECTED

    def test_json_render_dispatch(self, capsys) -> None:
        result = OptimizeResult(run_id=_RUN_ID, source_path="missing.png", error=_ERROR)
        outcome = CliOutcome(result, as_json=True)
        assert render_outcome(outcome) is outcome
        captured = capsys.readouterr()
        assert json.loads(captured.out) == json.loads(result.model_dump_json())
        assert captured.err == ""


class TestRenderOutcome:
    """Rendering dispatches on the result type and hands the outcome on."""

    def test_renders_json_and_returns_outcome(self, capsys: pytest.CaptureFixture[str]) -> None:
        outcome = CliOutcome(ModelGetResult(error=_ERROR), as_json=True)

        assert render_outcome(outcome) is outcome
        assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_request"

    def test_renders_text_errors_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        render_outcome(CliOutcome(CommandResult(run_id=_RUN_ID, error=_ERROR), as_json=False))

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error: bad request" in captured.err


class _Strict(BaseModel):
    value: int = Field(gt=0)


class TestCliCommand:
    """The decorator turns expected failures into rejected outcomes."""

    def test_keeps_pixgen_error_code(self) -> None:
        @cli_command()
        def command(*, json: bool = False) -> CliOutcome:
            raise PixgenError(ErrorCode.MODEL_NOT_FOUND, "no such model")

        outcome = command(json=True)

        assert outcome.as_json is True
        assert isinstance(outcome.result, CommandResult)
        assert outcome.result.error == PublicError(
            code=ErrorCode.MODEL_NOT_FOUND, message="no such model"
        )
        assert exit_status(outcome.result) is ExitStatus.REJECTED

    async def test_maps_validation_error_in_async_command(self) -> None:
        @cli_command()
        async def command(*, json: bool = False) -> CliOutcome:
            _Strict(value=0)
            return CliOutcome(ModelListResult(), as_json=json)

        outcome = await command()

        assert outcome.as_json is False
        assert outcome.result.error is not None
        assert outcome.result.error.code == ErrorCode.INVALID_REQUEST

    def test_uses_custom_error_result(self) -> None:
        @cli_command(lambda error: ModelGetResult(error=error))
        def command(*, json: bool = False) -> CliOutcome:
            raise PixgenError(ErrorCode.MODEL_NOT_FOUND, "no such model")

        assert isinstance(command().result, ModelGetResult)

    def test_leaves_unexpected_exceptions_alone(self) -> None:
        @cli_command()
        def command(*, json: bool = False) -> CliOutcome:
            raise RuntimeError("bug")

        with pytest.raises(RuntimeError, match="bug"):
            command()

    def test_preserves_signature_for_cyclopts(self) -> None:
        def command(prompt: str, *, json: bool = False) -> CliOutcome:
            """Document the command."""
            return CliOutcome(ModelListResult(), as_json=json)

        wrapped = cli_command()(command)

        assert wrapped.__name__ == "command"
        assert wrapped.__doc__ == "Document the command."
        assert wrapped.__wrapped__ is command


def test_failure_outcome_rejects_with_public_error() -> None:
    outcome = failure_outcome(
        PixgenError(ErrorCode.INVALID_CONFIGURATION, "bad config"), as_json=False
    )

    assert outcome.result.error == PublicError(
        code=ErrorCode.INVALID_CONFIGURATION, message="bad config"
    )
    assert outcome.__cyclopts_returncode__() == ExitStatus.REJECTED


def test_render_outcome_passes_through_builtin_results(capsys: pytest.CaptureFixture[str]) -> None:
    assert render_outcome(None) is None
    assert capsys.readouterr().out == ""
