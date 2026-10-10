"""Test local optimisation command parsing and public outcomes."""

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from cyclopts.exceptions import CoercionError, UnknownOptionError
from pydantic import ValidationError

from pixgen.cli.optimize import build_optimize_app
from pixgen.cli.outcome import RESULT_ACTION
from pixgen.config.models import Settings
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.results import OptimizeResult, OptimizeVariantResult, PublicError, VariantStatus
from pixgen.optimization.application import OptimizeApplication
from pixgen.optimization.models import OptimizeRequest, OutputFormat

if TYPE_CHECKING:
    from cyclopts import App


class FakeOptimizeApplication(OptimizeApplication):
    """Record requests and return controlled public outcomes."""

    def __init__(self, *, statuses=(VariantStatus.COMPLETED,), error=None) -> None:
        super().__init__(Settings())
        self.requests = []
        self.statuses = statuses
        self.error = error

    def run(self, request: OptimizeRequest) -> OptimizeResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        variants = []
        for index, status in enumerate(self.statuses):
            if status is VariantStatus.FAILED:
                variant = OptimizeVariantResult(
                    name=f"variant-{index}",
                    status=status,
                    error=PublicError(code=ErrorCode.OPTIMIZATION_FAILED, message="encode failed"),
                )
            elif status is VariantStatus.SKIPPED:
                variant = OptimizeVariantResult(
                    name=f"variant-{index}", status=status, reason="would upscale"
                )
            else:
                variant = OptimizeVariantResult(
                    name=f"variant-{index}",
                    status=VariantStatus.PLANNED if request.dry_run else status,
                    output_path=Path(f"/output/variant-{index}.webp"),
                    format="WEBP",
                    width=320,
                    height=240,
                    output_bytes=None if request.dry_run else 100,
                )
            variants.append(variant)
        return OptimizeResult(
            run_id=uuid.UUID(int=1),
            source_path=request.source,
            dry_run=request.dry_run,
            variants=tuple(variants),
        )


def _app(application) -> App:
    app = build_optimize_app(application)
    app.result_action = RESULT_ACTION
    return app


class TestOptimizeParsing:
    def test_passes_positional_source_repeated_flags_and_named_options(self) -> None:
        application = FakeOptimizeApplication()
        app = _app(application)
        command, bound, _ = app.parse_args(
            [
                "source.png",
                "--web",
                "--fit",
                "640x480",
                "--fit",
                "320x240",
                "--cover",
                "100x100",
                "--cover",
                "200x200",
                "--width",
                "300",
                "--width",
                "600",
                "--height",
                "400",
                "--height",
                "800",
                "--format",
                "webp",
                "--quality",
                "82",
                "--output",
                "result.webp",
                "--output-dir",
                "outputs",
                "--dry-run",
                "--mkdir",
                "--force",
                "--json",
            ],
            print_error=False,
            exit_on_error=False,
        )

        outcome = command(*bound.args, **bound.kwargs)

        assert outcome.as_json is True
        assert application.requests == [
            OptimizeRequest(
                source=Path("source.png"),
                web=True,
                fit=("640x480", "320x240"),
                cover=("100x100", "200x200"),
                width=(300, 600),
                height=(400, 800),
                format=OutputFormat.WEBP,
                quality=82,
                output=Path("result.webp"),
                output_dir=Path("outputs"),
                dry_run=True,
                mkdir=True,
                force=True,
            )
        ]

    def test_defaults_leave_request_planning_to_application(self) -> None:
        application = FakeOptimizeApplication()
        app = _app(application)
        command, bound, _ = app.parse_args(["source.png"], print_error=False, exit_on_error=False)

        command(*bound.args, **bound.kwargs)

        assert application.requests == [OptimizeRequest(source=Path("source.png"))]

    def test_rejects_packed_variant_flag(self) -> None:
        with pytest.raises(UnknownOptionError):
            _app(FakeOptimizeApplication()).parse_args(
                ["source.png", "--variant", "small=fit:320x240"],
                print_error=False,
                exit_on_error=False,
            )

    @pytest.mark.parametrize("format_value", ["gif", ""], ids=["unsupported", "empty"])
    def test_rejects_invalid_format_before_application(self, format_value) -> None:
        application = FakeOptimizeApplication()
        with pytest.raises(CoercionError):
            _app(application).parse_args(
                ["source.png", "--format", format_value], print_error=False, exit_on_error=False
            )
        assert application.requests == []

    @pytest.mark.parametrize("format_value", list(OutputFormat), ids=lambda value: value.value)
    def test_accepts_format_enum_choices(self, format_value) -> None:
        _, bound, _ = _app(FakeOptimizeApplication()).parse_args(
            ["source.png", "--format", format_value.value],
            print_error=False,
            exit_on_error=False,
        )
        assert bound.arguments["format"] is format_value


class TestOptimizeOutcomes:
    def test_help_describes_flags_without_running_application(self, capsys) -> None:
        application = FakeOptimizeApplication()
        with pytest.raises(SystemExit) as exc_info:
            _app(application)(["--help"])
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        for option in (
            "SOURCE",
            "--web",
            "--fit",
            "--cover",
            "--width",
            "--height",
            "--format",
            "--quality",
            "--output",
            "--output-dir",
            "--dry-run",
            "--mkdir",
            "--force",
            "--json",
        ):
            assert option in output
        assert "--variant" not in output
        assert application.requests == []

    def test_json_dry_run_preserves_planned_states(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _app(FakeOptimizeApplication())(["source.png", "--dry-run", "--json"])
        assert exc_info.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["source_path"] == "source.png"
        assert payload["dry_run"] is True
        assert payload["variants"][0]["status"] == "planned"
        assert payload["variants"][0]["output_bytes"] is None

    @pytest.mark.parametrize(
        ("statuses", "expected"),
        [
            ((VariantStatus.COMPLETED,), 0),
            ((VariantStatus.SKIPPED,), 0),
            ((VariantStatus.FAILED,), 3),
            ((VariantStatus.FAILED, VariantStatus.SKIPPED), 3),
            ((VariantStatus.COMPLETED, VariantStatus.FAILED), 4),
        ],
        ids=["completed", "skipped", "failed", "failed-and-skipped", "partial"],
    )
    def test_exit_codes_follow_public_results(self, statuses, expected, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _app(FakeOptimizeApplication(statuses=statuses))(["source.png", "--json"])
        assert exc_info.value.code == expected
        assert json.loads(capsys.readouterr().out)["error"] is None

    def test_command_failure_uses_optimize_result(self, capsys) -> None:
        application = FakeOptimizeApplication(
            error=PixgenError(ErrorCode.INVALID_REQUEST, "invalid optimisation request")
        )
        with pytest.raises(SystemExit) as exc_info:
            _app(application)(["source.png", "--json"])
        assert exc_info.value.code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["variants"] == []
        assert payload["error"]["code"] == "invalid_request"
        assert payload["source_path"] == "source.png"

    def test_validation_failure_retains_source_and_dry_run(self, capsys) -> None:
        with pytest.raises(ValidationError) as validation:
            OptimizeRequest.model_validate({"source": None})
        application = FakeOptimizeApplication(error=validation.value)

        with pytest.raises(SystemExit) as exc_info:
            _app(application)(["source.png", "--dry-run", "--json"])

        assert exc_info.value.code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["source_path"] == "source.png"
        assert payload["dry_run"] is True
        assert payload["error"]["code"] == "invalid_request"

    def test_unexpected_application_error_propagates(self) -> None:
        with pytest.raises(RuntimeError, match="application bug"):
            _app(FakeOptimizeApplication(error=RuntimeError("application bug")))(["source.png"])
