"""Tests for root shared image commands."""

from typing import TYPE_CHECKING

import pytest

from pixgen.cli.image import build_operation_app
from pixgen.cli.invoke import CommandInvoker
from pixgen.core.models import ImageOperation
from pixgen.core.results import CommandResult

if TYPE_CHECKING:
    from pixgen.application import RunOutcome


class RecordingApplication:
    """Fail the test if a validation-rejected request ever reaches run()."""

    async def run(self, *_args, **_kwargs) -> RunOutcome:
        pytest.fail("application.run() must not be called for an invalid request")


@pytest.mark.parametrize(
    ("operation", "argv"),
    [
        (ImageOperation.IMAGE_CREATE, ["   "]),
        (ImageOperation.IMAGE_EDIT, ["   ", "--image", "missing.png"]),
    ],
)
async def test_invalid_prompt_exits_cleanly_without_running(
    operation: ImageOperation, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    app = build_operation_app(operation, CommandInvoker(RecordingApplication()), ())
    command, bound, _ = app.parse_args(argv, print_error=False, exit_on_error=False)

    with pytest.raises(SystemExit) as exc_info:
        await command(*bound.args, **bound.kwargs)

    assert exc_info.value.code == 2
    assert "Error:" in capsys.readouterr().err


async def test_invalid_prompt_as_json_reports_public_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE, CommandInvoker(RecordingApplication()), ()
    )
    command, bound, _ = app.parse_args(["   ", "--json"], print_error=False, exit_on_error=False)

    with pytest.raises(SystemExit) as exc_info:
        await command(*bound.args, **bound.kwargs)

    assert exc_info.value.code == 2
    result = CommandResult.model_validate_json(capsys.readouterr().out)
    assert result.error is not None
    assert result.error.code == "invalid_request"
