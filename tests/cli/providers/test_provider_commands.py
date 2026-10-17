"""Tests for provider-native Cyclopts commands."""

from functools import partial
from typing import TYPE_CHECKING

import httpx2
import pytest
from cyclopts.exceptions import UnknownOptionError
from PIL import Image

from pixgen.application import ImageApplication
from pixgen.cli.invoke import CommandInvoker
from pixgen.cli.outcome import ExitStatus, exit_status
from pixgen.config.models import Defaults, GenerationSettings, Settings
from pixgen.core.errors import ErrorCode
from pixgen.core.models import ImageOperation

if TYPE_CHECKING:
    from pixgen.core.parameters import ProviderParams
from pixgen.cli.providers import GEMINI_SPEC, OPENAI_SPEC, OPENROUTER_SPEC
from pixgen.cli.providers.native import build_native_app
from pixgen.providers.openrouter import OpenRouterGPTImageParams, OpenRouterProvider
from pixgen.providers.registry import ProviderRegistry

build_openai_app = partial(build_native_app, OPENAI_SPEC)
build_gemini_app = partial(build_native_app, GEMINI_SPEC)
build_openrouter_app = partial(build_native_app, OPENROUTER_SPEC)


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


class RecordingInvoker:
    """Capture native selections without running image generation."""

    def __init__(self) -> None:
        self.models: list[str] = []
        self.parameters: list[ProviderParams] = []

    async def invoke(self, _intent, selection, _options) -> None:
        self.models.append(selection.model)
        self.parameters.append(selection.parameters)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (
            "google/gemini-3.1-flash-image",
            "openrouter/google/gemini-3.1-flash-image",
        ),
        ("openrouter/meta/muse-image", "openrouter/meta/muse-image"),
        (
            "openai/gpt-image-2.5-sunburst",
            "openrouter/openai/gpt-image-2.5-sunburst",
        ),
    ],
    ids=["google", "already-prefixed", "openai"],
)
async def test_openrouter_native_commands_normalise_nested_model_names(
    model: str, expected: str
) -> None:
    invoker = RecordingInvoker()
    app = build_openrouter_app(ImageOperation.IMAGE_CREATE, invoker)
    command, bound, _ = app.parse_args(
        ["--model", model, "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    await command(*bound.args, **bound.kwargs)

    assert invoker.models == [expected]


@pytest.mark.parametrize(
    ("build_app", "model"),
    [
        (build_openai_app, "google/gemini-3.1-flash-image"),
        (build_gemini_app, "openai/gpt-image-2.5-sunburst"),
    ],
    ids=["openai", "gemini"],
)
async def test_existing_provider_commands_still_reject_nested_local_names(
    build_app, model: str
) -> None:
    app = build_app(ImageOperation.IMAGE_CREATE, FailingInvoker())
    command, bound, _ = app.parse_args(
        ["--model", model, "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    outcome = await command(*bound.args, **bound.kwargs)

    assert outcome.result.error.code is ErrorCode.INVALID_REQUEST


async def test_openrouter_cli_resolves_native_flags_from_selected_model() -> None:
    invoker = RecordingInvoker()
    app = build_openrouter_app(ImageOperation.IMAGE_CREATE, invoker)
    command, bound, _ = app.parse_args(
        [
            "--model",
            "openai/gpt-image-2.5-sunburst",
            "--quality",
            "max",
            "--aspect-ratio",
            "auto",
            "--output-compression",
            "52",
            "A forest",
        ],
        print_error=False,
        exit_on_error=False,
    )

    await command(*bound.args, **bound.kwargs)

    params = invoker.parameters[0]
    assert isinstance(params, OpenRouterGPTImageParams)
    assert params.quality == "max"
    assert params.aspect_ratio == "auto"
    assert params.output_compression == 52


async def test_openrouter_cli_rejects_muse_edit_before_provider_generation(tmp_path) -> None:
    image_path = tmp_path / "input.png"
    Image.new("RGB", (2, 2)).save(image_path)
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda _request: pytest.fail("provider must not be called"))
    )
    provider = OpenRouterProvider(client)
    registry = ProviderRegistry((provider,))
    settings = Settings.model_construct(
        defaults=Defaults(image_edit_models=("openrouter/meta/muse-image",)),
        generation=GenerationSettings(),
    )
    invoker = CommandInvoker(ImageApplication(registry, settings))
    app = build_openrouter_app(ImageOperation.IMAGE_EDIT, invoker)
    command, bound, _ = app.parse_args(
        ["--image", str(image_path), "--model", "meta/muse-image", "Edit the lighthouse"],
        print_error=False,
        exit_on_error=False,
    )

    outcome = await command(*bound.args, **bound.kwargs)

    assert outcome.result.error.code is ErrorCode.INVALID_REQUEST
    assert "does not support image-edit" in outcome.result.error.message
    await client.aclose()
