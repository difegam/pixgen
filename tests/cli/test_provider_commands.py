"""Tests for provider-owned Cyclopts commands."""

import pytest
from cyclopts.exceptions import UnknownOptionError

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
