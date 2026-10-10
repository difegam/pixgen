"""Build the local image optimisation command."""

import uuid
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.outcome import CliOutcome, cli_command
from pixgen.core.results import OptimizeResult
from pixgen.optimization.models import OptimizeRequest, OutputFormat

if TYPE_CHECKING:
    from pixgen.core.results import PublicError
    from pixgen.optimization.application import OptimizeApplication

__all__: list[str] = ["build_optimize_app"]


def build_optimize_app(application: OptimizeApplication) -> App:
    """Build a provider-free app with ordinary named optimisation options."""
    app = App(name="optimize", group="Operations")

    @app.default
    def optimize(
        source: Path,
        *,
        web: bool = False,
        fit: list[str] | None = None,
        cover: list[str] | None = None,
        width: list[int] | None = None,
        height: list[int] | None = None,
        format: OutputFormat | None = None,  # noqa: A002
        quality: int | None = None,
        output: Path | None = None,
        output_dir: Path | None = None,
        dry_run: bool = False,
        mkdir: bool = False,
        force: bool = False,
        json: bool = False,
    ) -> CliOutcome:
        """Optimise a local image with Pillow.

        Args:
            source: Local image to optimise.
            web: Expand the website variant preset.
            fit: Fit within WIDTHxHEIGHT bounds. Repeat for additional variants.
            cover: Crop to WIDTHxHEIGHT dimensions. Repeat for additional variants.
            width: Resize to a width. Repeat for additional variants.
            height: Resize to a height. Repeat for additional variants.
            format: Keep the source format or select an output encoding.
            quality: Override lossy encoder quality.
            output: Set the path for one output; a bare name gets the format's extension.
            output_dir: Place named variants in this directory.
            dry_run: Report planned outputs without writing files.
            mkdir: Permit creating an explicit output directory.
            force: Permit replacing existing output files.
            json: Render the public result as JSON.
        """

        def optimize_error(error: PublicError) -> OptimizeResult:
            """Retain the invocation's source when command validation fails."""
            return OptimizeResult(
                run_id=uuid.uuid4(), source_path=source, dry_run=dry_run, error=error
            )

        @cli_command(optimize_error)
        def invoke(*, json: bool) -> CliOutcome:
            """Build and execute the request inside the expected-error boundary."""
            request = OptimizeRequest(
                source=source,
                web=web,
                fit=tuple(fit or ()),
                cover=tuple(cover or ()),
                width=tuple(width or ()),
                height=tuple(height or ()),
                format=format,
                quality=quality,
                output=output,
                output_dir=output_dir,
                dry_run=dry_run,
                mkdir=mkdir,
                force=force,
            )
            return CliOutcome(application.run(request), as_json=json)

        return invoke(json=json)

    return app
