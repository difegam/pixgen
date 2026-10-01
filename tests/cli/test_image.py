"""Tests for root shared image commands."""

from typing import TYPE_CHECKING
from uuid import uuid7

import pytest
from cyclopts.exceptions import UnknownOptionError, ValidationError

from pixgen.cli.image import build_operation_app
from pixgen.cli.invoke import CommandInvoker
from pixgen.cli.outcome import ExitStatus, exit_status
from pixgen.config.models import ModelGroup
from pixgen.core.errors import ErrorCode
from pixgen.core.models import ImageOperation
from pixgen.core.results import CommandResult, TargetResult

if TYPE_CHECKING:
    from pixgen.core.requests import SharedSelection


class RecordingApplication:
    """Fail the test if a validation-rejected request ever reaches run()."""

    async def run(self, *_args, **_kwargs) -> CommandResult:
        pytest.fail("application.run() must not be called for an invalid request")


class CapturingApplication:
    """Capture the selection passed to the application."""

    def __init__(self) -> None:
        self.selection: SharedSelection | None = None

    async def run(self, _intent, *, selection, **_kwargs) -> CommandResult:
        self.selection = selection
        return CommandResult(
            run_id=uuid7(),
            results=(
                TargetResult(
                    model="openai/gpt-image-2",
                    variant=1,
                    artifact_path="output.png",
                    media_type="image/png",
                ),
            ),
        )


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


def test_create_accepts_group() -> None:
    group = ModelGroup(
        models=("openai/gpt-image-2", "gemini/gemini-3.1-flash-image"),
        description="Product image models",
    )
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE,
        CommandInvoker(CapturingApplication()),
        (),
        groups={"product-hero": group},
    )

    _command, bound, _ = app.parse_args(
        ["--group", "product-hero", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    assert bound.arguments["group"] == "product-hero"


def test_create_rejects_group_and_model_together() -> None:
    group = ModelGroup(models=("openai/gpt-image-2",), description="Product image models")
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE,
        CommandInvoker(CapturingApplication()),
        (),
        groups={"product-hero": group},
    )

    with pytest.raises(ValidationError):
        app.parse_args(
            ["--group", "product-hero", "--model", "openai/gpt-image-2", "A forest"],
            print_error=False,
            exit_on_error=False,
        )


def test_edit_rejects_group() -> None:
    app = build_operation_app(ImageOperation.IMAGE_EDIT, CommandInvoker(RecordingApplication()), ())

    with pytest.raises(UnknownOptionError):
        app.parse_args(
            ["--group", "product-hero", "--image", "source.png", "A forest"],
            print_error=False,
            exit_on_error=False,
        )


def test_create_rejects_shared_aspect_ratio() -> None:
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE, CommandInvoker(RecordingApplication()), ()
    )

    with pytest.raises(UnknownOptionError):
        app.parse_args(
            ["--aspect-ratio", "16:9", "A forest"],
            print_error=False,
            exit_on_error=False,
        )


def test_edit_keeps_shared_aspect_ratio() -> None:
    app = build_operation_app(ImageOperation.IMAGE_EDIT, CommandInvoker(RecordingApplication()), ())

    _command, bound, _ = app.parse_args(
        ["--aspect-ratio", "3:2", "--image", "source.png", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    assert bound.arguments["aspect_ratio"] == "3:2"


async def test_create_resolves_group_models_before_invocation() -> None:
    application = CapturingApplication()
    group = ModelGroup(
        models=("openai/gpt-image-2", "gemini/gemini-3.1-flash-image"),
        description="Product image models",
    )
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE,
        CommandInvoker(application),
        (),
        groups={"product-hero": group},
    )
    command, bound, _ = app.parse_args(
        ["--group", "product-hero", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    await command(*bound.args, **bound.kwargs)

    assert application.selection is not None
    assert application.selection.models == group.models


async def test_create_unknown_group_returns_invalid_request_without_invoking() -> None:
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE,
        CommandInvoker(RecordingApplication()),
        (),
        groups={},
    )
    command, bound, _ = app.parse_args(
        ["--group", "missing", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    outcome = await command(*bound.args, **bound.kwargs)

    assert exit_status(outcome.result) is ExitStatus.REJECTED
    assert outcome.result.error is not None
    assert outcome.result.error.code is ErrorCode.INVALID_REQUEST


async def test_create_without_group_keeps_default_selection_path() -> None:
    application = CapturingApplication()
    app = build_operation_app(
        ImageOperation.IMAGE_CREATE,
        CommandInvoker(application),
        (),
    )
    command, bound, _ = app.parse_args(
        ["A forest"],
        print_error=False,
        exit_on_error=False,
    )

    await command(*bound.args, **bound.kwargs)

    assert application.selection is not None
    assert application.selection.models is None
