"""Tests for the root Pixgen command tree."""

import pytest
from cyclopts import App
from cyclopts.exceptions import UnknownCommandError, UnknownOptionError

from pixgen.application import ImageApplication
from pixgen.cli.app import build_app
from pixgen.config.models import Settings
from pixgen.core.models import ImageOperation, ModelSpec
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.gemini_cli import GeminiCliFactory
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.openai_cli import OpenAICliFactory
from pixgen.providers.registry import ProviderRegistry


class UnregisteredFactory:
    """Factory whose provider is absent from the registry."""

    name = "example"
    operations = frozenset({ImageOperation.IMAGE_CREATE})

    def build(self, _operation: ImageOperation, _invoker: object) -> App:
        """Build a placeholder provider app."""
        return App(name=self.name)


class CreateOnlyProvider:
    """Provider catalogue entry used to validate factory operations."""

    name = "example"

    def models(self) -> tuple[ModelSpec, ...]:
        """Return one create-only model."""
        from tests.factories import make_model_spec

        return (
            make_model_spec(
                model_id="example/demo",
                operations=frozenset({ImageOperation.IMAGE_CREATE}),
            ),
        )


class EditOnlyFactory(UnregisteredFactory):
    """Factory that declares an operation its provider does not support."""

    name = "example"
    operations = frozenset({ImageOperation.IMAGE_EDIT})


@pytest.fixture
def app() -> App:
    """Build a credential-free root app for parser tests."""
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))
    return build_app(
        ImageApplication(registry, Settings()),
        registry,
        (OpenAICliFactory(), GeminiCliFactory()),
    )


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


@pytest.mark.parametrize(
    ("arguments", "command_name"),
    [
        (["create", "A forest"], "create"),
        (["edit", "--image", "source.png", "Add mist"], "edit"),
    ],
)
def test_shared_operations_keep_generation_feedback_internal(app, arguments, command_name) -> None:
    command, bound, _ = app.parse_args(arguments, print_error=False, exit_on_error=False)

    assert command.__name__ == command_name
    assert "verbose" not in bound.arguments
    assert "progress" not in bound.arguments


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


def test_root_app_rejects_factory_without_registered_provider() -> None:
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))

    with pytest.raises(ValueError, match="is not registered"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (OpenAICliFactory(), GeminiCliFactory(), UnregisteredFactory()),
        )


def test_root_app_rejects_missing_provider_factory() -> None:
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))

    with pytest.raises(ValueError, match="lack CLI factories"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (OpenAICliFactory(),),
        )


def test_root_app_rejects_duplicate_factory_names() -> None:
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))

    with pytest.raises(ValueError, match="duplicate provider CLI name"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (OpenAICliFactory(), OpenAICliFactory(), GeminiCliFactory()),
        )


def test_root_app_rejects_factory_operation_absent_from_provider() -> None:
    registry = ProviderRegistry((CreateOnlyProvider(),))

    with pytest.raises(ValueError, match="declares unsupported operations"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (EditOnlyFactory(),),
        )
