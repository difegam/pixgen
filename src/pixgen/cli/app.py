"""Root CLI app builder and console entry point."""

import importlib.metadata
import sys
from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.group import build_group_app
from pixgen.cli.image import build_operation_app
from pixgen.cli.invoke import CommandInvoker
from pixgen.cli.model import build_model_app
from pixgen.cli.optimize import build_optimize_app
from pixgen.cli.outcome import RESULT_ACTION, failure_outcome, render_outcome
from pixgen.core.errors import PixgenError
from pixgen.core.models import ImageOperation

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pixgen.application import ImageApplication
    from pixgen.cli.contracts import ProviderCliFactory
    from pixgen.cli.selector import ModelSelector
    from pixgen.config.models import ModelGroup
    from pixgen.config.writer import ConfigRepository
    from pixgen.optimization.application import OptimizeApplication
    from pixgen.providers.registry import ProviderRegistry

__all__: list[str] = [
    "build_app",
    "main",
]


def _get_version() -> str:
    try:
        return importlib.metadata.version("pixgen")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def default() -> None:
    """Generate and edit images with curated AI models.

    [Docs](https://github.com/difegam/pixgen) | [GitHub](https://github.com/difegam/pixgen)
    """


def build_app(
    application: ImageApplication,
    registry: ProviderRegistry,
    factories: tuple[ProviderCliFactory, ...],
    group_repository: ConfigRepository,
    optimize_application: OptimizeApplication,
    groups: Mapping[str, ModelGroup] | None = None,
    group_selector: ModelSelector | None = None,
) -> App:
    """Build the Pixgen app."""
    _validate_factories(registry, factories)
    app = App(
        name="pixgen",
        version=_get_version,
        help_format="markdown",
        result_action=RESULT_ACTION,
    )
    invoker = CommandInvoker(application)

    app.command(build_operation_app(ImageOperation.IMAGE_CREATE, invoker, factories, groups=groups))
    app.command(build_operation_app(ImageOperation.IMAGE_EDIT, invoker, factories, groups=groups))
    app.command(build_model_app(registry))
    app.command(build_optimize_app(optimize_application))
    app.command(
        build_group_app(
            registry,
            group_repository,
            group_selector,
        )
    )
    app.default(default)
    app.register_install_completion_command()

    return app


def main() -> None:
    """Console entry point for pixgen."""
    from pixgen.runtime import build_runtime

    try:
        runtime = build_runtime(require_config_file=sys.argv[1:2] != ["group"])
    except PixgenError as exc:
        outcome = render_outcome(failure_outcome(exc, as_json="--json" in sys.argv[1:]))
        sys.exit(outcome.__cyclopts_returncode__())
    app = build_app(
        runtime.application,
        runtime.registry,
        runtime.cli_factories,
        runtime.group_repository,
        runtime.optimize_application,
        groups=runtime.settings.groups,
    )
    app()


def _validate_factories(
    registry: ProviderRegistry,
    factories: tuple[ProviderCliFactory, ...],
) -> None:
    """Validate that CLI factories exactly cover registered providers."""
    providers = {provider.name: provider for provider in registry.providers()}
    factory_names: set[str] = set()
    for factory in factories:
        if factory.name in factory_names:
            raise ValueError(f"duplicate provider CLI name: {factory.name!r}")
        provider = providers.get(factory.name)
        if provider is None:
            raise ValueError(f"CLI factory {factory.name!r} is not registered")
        supported_operations = {
            operation
            for definition in provider.catalogue
            for operation in definition.spec.operations
        }
        unsupported_operations = factory.operations - supported_operations
        if unsupported_operations:
            raise ValueError(
                f"CLI factory {factory.name!r} declares unsupported operations: "
                f"{sorted(operation.value for operation in unsupported_operations)!r}"
            )
        factory_names.add(factory.name)
    missing = set(providers) - factory_names
    if missing:
        raise ValueError(f"registered providers lack CLI factories: {sorted(missing)!r}")
