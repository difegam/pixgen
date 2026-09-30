from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.render import render_command_result
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent

if TYPE_CHECKING:
    from pixgen.application import ImageApplication

__all__: list[str] = [
    "build_image_app",
]


def build_image_app(application: ImageApplication) -> App:
    """Build the image sub-app."""
    app = App(name="image", help="Image creation and editing commands")

    @app.command
    async def create(
        prompt: str,
        *,
        reference: list[Path] | None = None,
        model: list[str] | None = None,
        variants: int = 1,
        param: list[str] | None = None,
        output: Path | None = None,
        output_dir: Path | None = None,
        timeout_seconds: int | None = None,
        mkdir: bool = False,
        force: bool = False,
        json: bool = False,
    ) -> None:
        """Create images from a prompt and optional references."""
        references = tuple(reference or [])
        intent = ImageCreateIntent(prompt=prompt, references=references)
        model_ids = model or None

        outcome = await application.run(
            intent,
            models=model_ids,
            variants=variants,
            output=output,
            output_dir=output_dir,
            mkdir=mkdir,
            force=force,
            timeout_seconds=timeout_seconds,
            raw_params=param,
        )

        render_command_result(outcome.result, as_json=json)
        raise SystemExit(outcome.exit_code)

    @app.command
    async def edit(
        prompt: str,
        *,
        image: list[Path],
        model: list[str] | None = None,
        variants: int = 1,
        param: list[str] | None = None,
        output: Path | None = None,
        output_dir: Path | None = None,
        timeout_seconds: int | None = None,
        mkdir: bool = False,
        force: bool = False,
        json: bool = False,
    ) -> None:
        """Edit one or more source images through a prompt."""
        intent = ImageEditIntent(prompt=prompt, images=tuple(image))
        model_ids = model or None

        outcome = await application.run(
            intent,
            models=model_ids,
            variants=variants,
            output=output,
            output_dir=output_dir,
            mkdir=mkdir,
            force=force,
            timeout_seconds=timeout_seconds,
            raw_params=param,
        )

        render_command_result(outcome.result, as_json=json)
        raise SystemExit(outcome.exit_code)

    return app
