"""Build Gemini-owned Cyclopts image commands."""

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Parameter

from pixgen.cli.options import ExecutionOptions
from pixgen.core.models import ImageOperation
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent, NativeSelection
from pixgen.providers.gemini import GeminiParams

if TYPE_CHECKING:
    from pixgen.cli.invoke import CommandInvoker

__all__: list[str] = ["GeminiCliFactory", "build_gemini_app"]

_DEFAULT_GEMINI_PARAMS = GeminiParams()


def _model_id(value: str) -> str:
    """Validate and canonicalise a Gemini-local model name."""
    if value.startswith("gemini/"):
        return value
    if "/" in value:
        raise ValueError("Gemini native commands require a Gemini model name")
    return f"gemini/{value}"


def build_gemini_app(operation: ImageOperation, invoker: CommandInvoker) -> App:
    """Build one Gemini provider sub-app."""
    app = App(name="gemini", help="Gemini image generation options")

    if operation is ImageOperation.IMAGE_CREATE:

        @app.default
        async def create(
            prompt: str,
            *,
            model: str,
            params: Annotated[GeminiParams, Parameter(name="*")] = _DEFAULT_GEMINI_PARAMS,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> None:
            """Create an image with Gemini native parameters."""
            await _invoke(
                invoker,
                ImageCreateIntent(prompt=prompt),
                _model_id(model),
                params,
                ExecutionOptions(
                    variants=variants,
                    output=output,
                    output_dir=output_dir,
                    mkdir=mkdir,
                    force=force,
                    timeout_seconds=timeout_seconds,
                    json=json,
                ),
            )

    else:

        @app.default
        async def edit(
            prompt: str,
            *,
            image: list[Path],
            model: str,
            params: Annotated[GeminiParams, Parameter(name="*")] = _DEFAULT_GEMINI_PARAMS,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> None:
            """Edit images with Gemini native parameters."""
            await _invoke(
                invoker,
                ImageEditIntent(prompt=prompt, images=tuple(image)),
                _model_id(model),
                params,
                ExecutionOptions(
                    variants=variants,
                    output=output,
                    output_dir=output_dir,
                    mkdir=mkdir,
                    force=force,
                    timeout_seconds=timeout_seconds,
                    json=json,
                ),
            )

    return app


async def _invoke(
    invoker: CommandInvoker,
    intent,
    model: str,
    params: GeminiParams,
    options: ExecutionOptions,
) -> None:
    """Invoke a Gemini typed command."""
    await invoker.invoke(intent, NativeSelection(model=model, parameters=params), options)


class GeminiCliFactory:
    """Build Gemini provider commands."""

    name = "gemini"
    operations = frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT})

    def build(self, operation: ImageOperation, invoker: CommandInvoker) -> App:
        """Return a Gemini app for one operation."""
        return build_gemini_app(operation, invoker)
