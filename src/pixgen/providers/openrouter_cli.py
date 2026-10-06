"""Build OpenRouter-owned Cyclopts image commands."""

from functools import partial
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated, Literal

from cyclopts import App, Parameter
from pydantic import Field

from pixgen.cli.options import ExecutionOptions
from pixgen.cli.outcome import CliOutcome, cli_command
from pixgen.core.models import ImageOperation
from pixgen.core.parameters import ProviderParams
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent, NativeSelection
from pixgen.providers.openrouter import OPENROUTER_CATALOGUE
from pixgen.providers.shared import normalize_model_id

if TYPE_CHECKING:
    from pixgen.cli.invoke import CommandInvoker

__all__: list[str] = ["OpenRouterCliFactory", "build_openrouter_app"]

OpenRouterCliAspectRatio = Literal[
    "auto",
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:1",
    "4:3",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
]


class OpenRouterCliParams(ProviderParams):
    """Collect model-native flags before resolving them against the selected model."""

    aspect_ratio: OpenRouterCliAspectRatio | None = Field(default=None)
    resolution: Literal["512", "1K", "2K", "4K"] | None = Field(default=None)
    quality: Literal["auto", "low", "medium", "high", "xhigh", "max"] | None = Field(default=None)
    background: Literal["auto", "transparent", "opaque"] | None = Field(default=None)
    output_compression: int | None = Field(default=None, ge=0, le=100)


_DEFAULT_OPENROUTER_PARAMS = OpenRouterCliParams()
_model_id = partial(
    normalize_model_id,
    prefix="openrouter",
    error_message="OpenRouter native commands require an OpenRouter model name",
    allow_nested=True,
)


def _native_selection(model: str, params: OpenRouterCliParams) -> NativeSelection:
    model_id = _model_id(model)
    values = params.model_dump(exclude_none=True)
    definition = next(
        (item for item in OPENROUTER_CATALOGUE if item.spec.id == model_id),
        None,
    )
    parameter_type = definition.parameter_type if definition is not None else OpenRouterCliParams
    return NativeSelection(
        model=model_id,
        parameters=parameter_type.model_validate(values),
    )


def build_openrouter_app(operation: ImageOperation, invoker: CommandInvoker) -> App:
    """Build one OpenRouter provider sub-app."""
    app = App(name="openrouter", help="OpenRouter image generation options")

    if operation is ImageOperation.IMAGE_CREATE:

        @app.default
        @cli_command()
        async def create(
            prompt: str,
            *,
            model: str,
            params: Annotated[OpenRouterCliParams, Parameter(name="*")] = (
                _DEFAULT_OPENROUTER_PARAMS
            ),
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> CliOutcome:
            """Create an image with OpenRouter native parameters."""
            intent = ImageCreateIntent(prompt=prompt)
            selection = _native_selection(model, params)
            options = ExecutionOptions(
                variants=variants,
                output=output,
                output_dir=output_dir,
                mkdir=mkdir,
                force=force,
                timeout_seconds=timeout_seconds,
                json=json,
            )
            return await invoker.invoke(intent, selection, options)

    else:

        @app.default
        @cli_command()
        async def edit(
            prompt: str,
            *,
            image: list[Path],
            model: str,
            params: Annotated[OpenRouterCliParams, Parameter(name="*")] = (
                _DEFAULT_OPENROUTER_PARAMS
            ),
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> CliOutcome:
            """Edit images with OpenRouter native parameters."""
            intent = ImageEditIntent(prompt=prompt, images=tuple(image))
            selection = _native_selection(model, params)
            options = ExecutionOptions(
                variants=variants,
                output=output,
                output_dir=output_dir,
                mkdir=mkdir,
                force=force,
                timeout_seconds=timeout_seconds,
                json=json,
            )
            return await invoker.invoke(intent, selection, options)

    return app


class OpenRouterCliFactory:
    """Build OpenRouter provider commands."""

    name = "openrouter"
    operations = frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT})

    def build(self, operation: ImageOperation, invoker: CommandInvoker) -> App:
        """Return an OpenRouter app for one operation."""
        return build_openrouter_app(operation, invoker)
