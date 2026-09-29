"""Tests for root shared image commands."""

import pytest

from pixgen.cli.image import build_operation_app
from pixgen.cli.invoke import CommandInvoker
from pixgen.cli.outcome import ExitStatus, exit_status
from pixgen.core.models import ImageOperation
from pixgen.core.results import CommandResult


class RecordingApplication:
    """Fail the test if a validation-rejected request ever reaches run()."""

    async def run(self, *_args, **_kwargs) -> CommandResult:
        pytest.fail("application.run() must not be called for an invalid request")


@pytest.mark.parametrize(
    ("operation", "argv"),
    [
        (ImageOperation.IMAGE_CREATE, ["   "]),
        (ImageOperation.IMAGE_EDIT, ["   ", "--image", "missing.png"]),
    ],
)
async def test_invalid_prompt_is_rejected_without_running(
    operation: ImageOperation, argv: list[str]
) -> None:
    app = build_operation_app(operation, CommandInvoker(RecordingApplication()), ())
    command, bound, _ = app.parse_args(argv, print_error=False, exit_on_error=False)

    outcome = await command(*bound.args, **bound.kwargs)

    assert exit_status(outcome.result) is ExitStatus.REJECTED
    assert outcome.result.error is not None
    assert outcome.result.error.code == "invalid_request"


async def test_invalid_prompt_as_json_selects_json_rendering() -> None:
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE, CommandInvoker(RecordingApplication()), ()
    )
    command, bound, _ = app.parse_args(["   ", "--json"], print_error=False, exit_on_error=False)

    outcome = await command(*bound.args, **bound.kwargs)

    assert outcome.as_json is True
    assert isinstance(outcome.result, CommandResult)
    assert outcome.result.error is not None
