"""Build root image operation apps and shared multi-model commands."""

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from cyclopts import App
from pydantic import ValidationError

from pixgen.cli.invoke import render_validation_error
from pixgen.cli.options import ExecutionOptions
from pixgen.core.models import ImageOperation
from pixgen.core.parameters import SharedImageParams
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent, SharedSelection

if TYPE_CHECKING:
    from pixgen.cli.contracts import ProviderCliFactory
    from pixgen.cli.invoke import CommandInvoker

__all__: list[str] = ["build_operation_app"]


def build_operation_app(
    operation: ImageOperation,
    invoker: CommandInvoker,
    factories: tuple[ProviderCliFactory, ...],
) -> App:
    """Build one root operation app with shared and native commands."""
    app = App(name="create" if operation is ImageOperation.IMAGE_CREATE else "edit")

    if operation is ImageOperation.IMAGE_CREATE:

        @app.default
        async def create(
            prompt: str,
            *,
            reference: list[Path] | None = None,
            model: list[str] | None = None,
            aspect_ratio: str | None = None,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> None:
            """Create images using shared parameters across selected models."""
            try:
                intent = ImageCreateIntent(prompt=prompt, references=tuple(reference or ()))
                selection = SharedSelection(
                    models=tuple(model) if model else None,
                    parameters=SharedImageParams(aspect_ratio=aspect_ratio),
                )
                options = ExecutionOptions(
                    variants=variants,
                    output=output,
                    output_dir=output_dir,
                    mkdir=mkdir,
                    force=force,
                    timeout_seconds=timeout_seconds,
                    json=json,
                )
            except ValidationError as exc:
                render_validation_error(exc, as_json=json)
            await invoker.invoke(intent, selection, options)

    else:

        @app.default
        async def edit(
            prompt: str,
            *,
            image: list[Path],
            model: list[str] | None = None,
            aspect_ratio: str | None = None,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> None:
            """Edit images using shared parameters across selected models."""
            try:
                intent = ImageEditIntent(prompt=prompt, images=tuple(image))
                selection = SharedSelection(
                    models=tuple(model) if model else None,
                    parameters=SharedImageParams(aspect_ratio=aspect_ratio),
                )
                options = ExecutionOptions(
                    variants=variants,
                    output=output,
                    output_dir=output_dir,
                    mkdir=mkdir,
                    force=force,
                    timeout_seconds=timeout_seconds,
                    json=json,
                )
            except ValidationError as exc:
                render_validation_error(exc, as_json=json)
            await invoker.invoke(intent, selection, options)

    for factory in factories:
        if operation in factory.operations:
            app.command(factory.build(operation, invoker))
    return app
