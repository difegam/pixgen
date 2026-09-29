"""Invoke typed image requests through the application."""

from typing import TYPE_CHECKING

from pixgen.cli.outcome import CliOutcome
from pixgen.cli.render import create_generation_progress

if TYPE_CHECKING:
    from pixgen.application import ImageApplication
    from pixgen.cli.options import ExecutionOptions
    from pixgen.core.requests import ImageIntent, ParameterSelection

__all__: list[str] = ["CommandInvoker"]


class CommandInvoker:
    """Bridge image commands to shared orchestration."""

    def __init__(self, application: ImageApplication) -> None:
        self._application = application

    async def invoke(
        self,
        intent: ImageIntent,
        selection: ParameterSelection,
        options: ExecutionOptions,
    ) -> CliOutcome:
        """Run one typed selection and return its outcome for rendering."""
        progress = create_generation_progress(as_json=options.as_json)
        try:
            result = await self._application.run(
                intent,
                selection=selection,
                variants=options.variants,
                output=options.output,
                output_dir=options.output_dir,
                mkdir=options.mkdir,
                force=options.force,
                timeout_seconds=options.timeout_seconds,
                observer=progress,
            )
        finally:
            if progress is not None:
                progress.stop()
        return CliOutcome(
            result,
            as_json=options.as_json,
            relative_output_paths=options.output is None and options.output_dir is None,
        )
