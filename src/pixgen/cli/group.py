"""Build the model-group creation command."""

import sys
from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.outcome import CliOutcome, cli_command
from pixgen.cli.selector import (
    InteractiveGroupSelection,
    InteractiveModelSelector,
    ModelSelector,
)
from pixgen.config.models import ModelGroup
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.results import GroupCreateResult, PublicError

if TYPE_CHECKING:
    from pixgen.config.writer import ConfigRepository
    from pixgen.providers.registry import ProviderRegistry

__all__: list[str] = [
    "build_group_app",
]


def _group_create_error(error: PublicError) -> GroupCreateResult:
    """Wrap a group creation failure in a group result."""
    return GroupCreateResult(error=error)


def build_group_app(
    registry: ProviderRegistry,
    repository: ConfigRepository,
    selector: ModelSelector | None = None,
) -> App:
    """Build the model-group command app."""
    app = App(name="group", help="Create reusable groups of image models.")
    active_selector = selector or InteractiveModelSelector()

    @app.command(name="create")
    @cli_command(_group_create_error)
    def create(
        name: str,
        *,
        model: list[str] | None = None,
        description: str | None = None,
        tag: list[str] | None = None,
        json: bool = False,
    ) -> CliOutcome:
        """Create a named group of curated image models."""
        if not name.strip():
            raise PixgenError(ErrorCode.INVALID_REQUEST, "group name must not be blank")

        requested_models = tuple(model or ())
        if requested_models:
            group = _build_explicit_group(
                registry,
                requested_models,
                description=description,
                tags=tuple(tag or ()),
            )
        else:
            if not _is_interactive_terminal():
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    "at least one --model is required outside an interactive terminal",
                )
            selected = active_selector.select(
                registry.models(),
                description=description,
                tags=tuple(tag or ()),
            )
            group = _build_interactive_group(selected)

        repository.create_group(name, group)
        return CliOutcome(
            GroupCreateResult(name=name, config_path=repository.path),
            as_json=json,
        )

    return app


def _build_explicit_group(
    registry: ProviderRegistry,
    models: tuple[str, ...],
    *,
    description: str | None,
    tags: tuple[str, ...],
) -> ModelGroup:
    if len(models) != len(set(models)):
        raise PixgenError(ErrorCode.INVALID_REQUEST, "models must not contain duplicate model IDs")
    if description is None:
        raise PixgenError(ErrorCode.INVALID_REQUEST, "--description is required with --model")
    for model_id in models:
        registry.get_model(model_id)
    return ModelGroup(models=models, description=description, tags=tags)


def _build_interactive_group(selection: InteractiveGroupSelection) -> ModelGroup:
    return ModelGroup(
        models=selection.models,
        description=selection.description,
        tags=selection.tags,
    )


def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
