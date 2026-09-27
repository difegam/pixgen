"""Invoke typed image requests through the application."""

from typing import TYPE_CHECKING

from pixgen.cli.render import render_command_result

if TYPE_CHECKING:
    from pixgen.application import ImageApplication
    from pixgen.cli.options import ExecutionOptions
    from pixgen.core.requests import ImageIntent, ParameterSelection

__all__: list[str] = ["CommandInvoker"]


class CommandInvoker:
    """Bridge provider commands to shared orchestration and rendering."""

    def __init__(self, application: ImageApplication) -> None:
        self._application = application

    async def invoke(
        self,
        intent: ImageIntent,
        selection: ParameterSelection,
        options: ExecutionOptions,
    ) -> None:
        """Run one typed selection and exit with the application status."""
        outcome = await self._application.run(
            intent,
            selection=selection,
            variants=options.variants,
            output=options.output,
            output_dir=options.output_dir,
            mkdir=options.mkdir,
            force=options.force,
            timeout_seconds=options.timeout_seconds,
        )
        render_command_result(outcome.result, as_json=options.as_json)
        raise SystemExit(outcome.exit_code)
