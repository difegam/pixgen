"""Root CLI app builder and console entry point."""

import importlib.metadata
from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.image import build_operation_app
from pixgen.cli.invoke import CommandInvoker
from pixgen.cli.model import build_model_app
from pixgen.core.models import ImageOperation

if TYPE_CHECKING:
    from pixgen.application import ImageApplication
    from pixgen.cli.contracts import ProviderCliFactory
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


def build_app(
    application: ImageApplication,
    registry: ProviderRegistry,
    factories: tuple[ProviderCliFactory, ...] | None = None,
) -> App:
    """Build the Pixgen app."""
    app = App(
        name="pixgen",
        help="Generate and edit images with curated AI models.",
        version=_get_version,
    )
    resolved_factories = tuple(factories) if factories is not None else registry.cli_factories()
    invoker = CommandInvoker(application)
    app.command(build_operation_app(ImageOperation.IMAGE_CREATE, invoker, resolved_factories))
    app.command(build_operation_app(ImageOperation.IMAGE_EDIT, invoker, resolved_factories))
    app.command(build_model_app(registry))
    return app


def main() -> None:
    """Console entry point for pixgen."""
    from pixgen.runtime import build_runtime

    application, registry, _settings = build_runtime()
    app = build_app(application, registry)
    app()
