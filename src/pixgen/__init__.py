"""Pixgen — Generate and edit images with curated AI models."""


import importlib.metadata
import logging

__all__: list[str] = [
    "__version__",
]


def _get_version() -> str:
    try:
        return importlib.metadata.version("pixgen")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


__version__ = _get_version()

# Library convention: stay silent unless the host application configures logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())
