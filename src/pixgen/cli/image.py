"""Build root image operation apps and shared multi-model commands."""

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Group, Parameter, validators

from pixgen.cli.options import ExecutionOptions
from pixgen.cli.outcome import CliOutcome, cli_command
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.models import ImageOperation
from pixgen.core.parameters import SharedImageParams
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent, SharedSelection

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pixgen.cli.contracts import ProviderCliFactory
    from pixgen.cli.invoke import CommandInvoker
    from pixgen.config.models import ModelGroup
    from pixgen.core.models import ModelId

__all__: list[str] = ["build_operation_app"]


def build_operation_app(
    operation: ImageOperation,
    invoker: CommandInvoker,
    factories: tuple[ProviderCliFactory, ...],
    groups: Mapping[str, ModelGroup] | None = None,
) -> App:
    """Build one root operation app with shared and native commands."""
    app = App(
        name="create" if operation is ImageOperation.IMAGE_CREATE else "edit",
        group="Operations",
    )

    image_prompt = Annotated[
        str,
        Parameter(
            group=(app.group_parameters,),
            help="Prompt describing the desired image.",
        ),
    ]
    model_parameter = Annotated[
        list[str] | None,
        Parameter(
            group=(app.group_parameters,),
            help="Models to use for the operation.",
        ),
    ]

    if operation is ImageOperation.IMAGE_CREATE:
        selection_group = Group(
            validator=validators.MutuallyExclusive(),
            help="Choose models directly or select a configured model group.",
        )
        create_model_parameter = Annotated[
            list[str] | None,
            Parameter(
                group=(selection_group, app.group_parameters),
                help="Models to use for the operation.",
            ),
        ]
        group_parameter = Annotated[
            str | None,
            Parameter(
                group=(selection_group, app.group_parameters),
                help="Configured model group to use for the operation.",
            ),
        ]
        configured_groups = groups or {}

        @app.default
        @cli_command()
        async def create(
            prompt: image_prompt,
            *,
            reference: list[Path] | None = None,
            model: create_model_parameter = None,
            group: group_parameter = None,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> CliOutcome:
            """Create images using shared parameters across selected models."""
            intent = ImageCreateIntent(prompt=prompt, references=tuple(reference or ()))
            selected_models = tuple(model) if model else None
            if group is not None:
                selected_models = _resolve_group(group, configured_groups)
            selection = SharedSelection(
                models=selected_models,
                parameters=SharedImageParams(),
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
            return await invoker.invoke(intent, selection, options)

    else:

        @app.default
        @cli_command()
        async def edit(
            prompt: image_prompt,
            *,
            image: list[Path],
            model: model_parameter = None,
            aspect_ratio: str | None = None,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> CliOutcome:
            """Edit images using shared parameters across selected models."""
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
            return await invoker.invoke(intent, selection, options)

    for factory in factories:
        if operation in factory.operations:
            app.command(factory.build(operation, invoker))
    return app


def _resolve_group(
    name: str,
    groups: Mapping[str, ModelGroup],
) -> tuple[ModelId, ...]:
    """Resolve one configured group to its ordered model IDs."""
    try:
        return groups[name].models
    except KeyError as exc:
        raise PixgenError(ErrorCode.INVALID_REQUEST, f"unknown model group: {name}") from exc
