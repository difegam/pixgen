"""Build Gemini-owned Cyclopts image commands."""

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Parameter

from pixgen.cli.options import ExecutionOptions
from pixgen.cli.outcome import CliOutcome, cli_command
from pixgen.core.errors import ErrorCode, PixgenError
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
        raise PixgenError(
            ErrorCode.INVALID_REQUEST, "Gemini native commands require a Gemini model name"
        )
    return f"gemini/{value}"


def build_gemini_app(operation: ImageOperation, invoker: CommandInvoker) -> App:
    """Build one Gemini provider sub-app."""
    app = App(name="gemini", help="Gemini image generation options")

    if operation is ImageOperation.IMAGE_CREATE:

        @app.default
        @cli_command()
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
        ) -> CliOutcome:
            """Create an image with Gemini native parameters."""
            intent = ImageCreateIntent(prompt=prompt)
            selection = NativeSelection(model=_model_id(model), parameters=params)
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
            params: Annotated[GeminiParams, Parameter(name="*")] = _DEFAULT_GEMINI_PARAMS,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> CliOutcome:
            """Edit images with Gemini native parameters."""
            intent = ImageEditIntent(prompt=prompt, images=tuple(image))
            selection = NativeSelection(model=_model_id(model), parameters=params)
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


class GeminiCliFactory:
    """Build Gemini provider commands."""

    name = "gemini"
    operations = frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT})

    def build(self, operation: ImageOperation, invoker: CommandInvoker) -> App:
        """Return a Gemini app for one operation."""
        return build_gemini_app(operation, invoker)
