"""Tests for provider-owned Cyclopts commands."""

import pytest
from cyclopts.exceptions import UnknownOptionError

from pixgen.cli.outcome import ExitStatus, exit_status
from pixgen.core.errors import ErrorCode
from pixgen.core.models import ImageOperation
from pixgen.providers.gemini_cli import build_gemini_app
from pixgen.providers.openai_cli import build_openai_app


class DummyInvoker:
    """Invoker used to parse provider commands without running generation."""

    async def invoke(self, *_args, **_kwargs) -> None:
        return None


def test_openai_native_options_are_flattened() -> None:
    app = build_openai_app(ImageOperation.IMAGE_CREATE, DummyInvoker())
    command, bound, _ = app.parse_args(
        ["--model", "gpt-image-2", "--quality", "high", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    assert command.__name__ == "create"
    assert bound.arguments["params"].quality == "high"
    assert bound.arguments["model"] == "gpt-image-2"


def test_gemini_native_options_are_flattened() -> None:
    app = build_gemini_app(ImageOperation.IMAGE_CREATE, DummyInvoker())
    _command, bound, _ = app.parse_args(
        ["--model", "gemini-3.1-flash-image", "--aspect-ratio", "16:9", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    assert bound.arguments["params"].aspect_ratio == "16:9"


def test_provider_apps_reject_foreign_native_options() -> None:
    app = build_openai_app(ImageOperation.IMAGE_CREATE, DummyInvoker())
    with pytest.raises(UnknownOptionError):
        app.parse_args(
            ["--model", "gpt-image-2", "--image-size", "2K", "A forest"],
            print_error=False,
            exit_on_error=False,
        )


class FailingInvoker:
    """Fail the test if a validation-rejected request ever reaches invoke()."""

    async def invoke(self, *_args, **_kwargs) -> None:
        pytest.fail("invoker.invoke() must not be called for an invalid request")


@pytest.mark.parametrize(
    ("build_app", "argv"),
    [
        (build_openai_app, ["--model", "gpt-image-2", "   "]),
        (build_gemini_app, ["--model", "gemini-3.1-flash-image", "   "]),
    ],
)
async def test_provider_apps_reject_invalid_prompt_without_invoking(build_app, argv) -> None:
    app = build_app(ImageOperation.IMAGE_CREATE, FailingInvoker())
    command, bound, _ = app.parse_args(argv, print_error=False, exit_on_error=False)

    outcome = await command(*bound.args, **bound.kwargs)

    assert exit_status(outcome.result) is ExitStatus.REJECTED
    assert outcome.result.error.code == ErrorCode.INVALID_REQUEST


@pytest.mark.parametrize(
    ("build_app", "argv"),
    [
        (build_openai_app, ["--model", "gemini/gemini-3.1-flash-image", "A forest"]),
        (build_gemini_app, ["--model", "openai/gpt-image-2", "A forest"]),
    ],
)
async def test_provider_apps_reject_foreign_model_without_invoking(build_app, argv) -> None:
    app = build_app(ImageOperation.IMAGE_CREATE, FailingInvoker())
    command, bound, _ = app.parse_args(argv, print_error=False, exit_on_error=False)

    outcome = await command(*bound.args, **bound.kwargs)

    assert outcome.result.error.code == ErrorCode.INVALID_REQUEST
    assert "native commands require" in outcome.result.error.message
