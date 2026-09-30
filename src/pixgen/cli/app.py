"""Root CLI app builder and console entry point."""

import importlib.metadata
from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.image import build_image_app
from pixgen.cli.model import build_model_app

if TYPE_CHECKING:
    from pixgen.application import ImageApplication
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
) -> App:
    """Build the Pixgen app."""
    app = App(
        name="pixgen",
        help="Generate and edit images with curated AI models.",
        version=_get_version,
    )
    app.command(build_image_app(application))
    app.command(build_model_app(registry))
    return app


def main() -> None:
    """Console entry point for pixgen."""
    from pixgen.runtime import build_runtime

    application, registry, _settings = build_runtime()
    app = build_app(application, registry)
    app()
