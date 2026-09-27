"""Tests for the root Pixgen command tree."""

from typing import TYPE_CHECKING

import pytest
from cyclopts.exceptions import UnknownCommandError, UnknownOptionError

from pixgen.application import ImageApplication
from pixgen.cli.app import build_app
from pixgen.config.models import Settings
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from cyclopts import App


@pytest.fixture
def app() -> App:
    """Build a credential-free root app for parser tests."""
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))
    return build_app(ImageApplication(registry, Settings()), registry)


def test_root_shared_create_accepts_repeated_models_and_ratio(app) -> None:
    command, bound, _ = app.parse_args(
        [
            "create",
            "--model",
            "openai/gpt-image-2",
            "--model",
            "gemini/gemini-3.1-flash-image",
            "--aspect-ratio",
            "16:9",
            "A forest",
        ],
        print_error=False,
        exit_on_error=False,
    )

    assert command.__name__ == "create"
    assert bound.arguments["model"] == [
        "openai/gpt-image-2",
        "gemini/gemini-3.1-flash-image",
    ]
    assert bound.arguments["aspect_ratio"] == "16:9"


def test_root_provider_subcommand_owns_native_flags(app) -> None:
    command, bound, _ = app.parse_args(
        ["create", "openai", "--model", "gpt-image-2", "--quality", "high", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    assert command.__name__ == "create"
    assert bound.arguments["params"].quality == "high"


def test_provider_name_prompt_can_be_disambiguated_with_prompt_option(app) -> None:
    _command, bound, _ = app.parse_args(
        ["create", "--prompt", "openai"],
        print_error=False,
        exit_on_error=False,
    )

    assert bound.arguments["prompt"] == "openai"


def test_removed_image_group_and_raw_parameter_option_are_rejected(app) -> None:
    with pytest.raises(UnknownCommandError):
        app.parse_args(["image", "create", "A forest"], print_error=False, exit_on_error=False)
    with pytest.raises(UnknownOptionError):
        app.parse_args(
            ["create", "--param", "quality=high", "A forest"],
            print_error=False,
            exit_on_error=False,
        )
