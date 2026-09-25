"""Pixgen — Generate and edit images with curated AI models."""


import importlib.metadata

__all__: list[str] = [
    "__version__",
]


def _get_version() -> str:
    try:
        return importlib.metadata.version("pixgen")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


__version__ = _get_version()
