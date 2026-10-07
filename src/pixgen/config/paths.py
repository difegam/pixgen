"""Resolve configuration file paths."""

import os
from pathlib import Path

from platformdirs import PlatformDirs

__all__: list[str] = [
    "resolve_config_path",
    "resolve_env_file_path",
]

_CONFIG_FILE_NAME = "config.toml"
_ENV_FILE_NAME = ".env"
_PIXGEN_CONFIG_ENV = "PIXGEN_CONFIG"


def resolve_config_path() -> Path:
    """Return the configuration file path.

    Uses PIXGEN_CONFIG environment variable if set (must be absolute),
    otherwise falls back to PlatformDirs user config directory.
    """
    env_path = os.environ.get(_PIXGEN_CONFIG_ENV)
    if env_path:
        path = Path(env_path)
        if not path.is_absolute():
            raise ValueError(f"{_PIXGEN_CONFIG_ENV} must be an absolute path, got: {env_path}")
        return path

    dirs = PlatformDirs(appname="pixgen")
    return dirs.user_config_path / _CONFIG_FILE_NAME


def resolve_env_file_path() -> Path:
    """Return the optional dotenv file path in the PlatformDirs user config directory."""
    dirs = PlatformDirs(appname="pixgen")
    return dirs.user_config_path / _ENV_FILE_NAME
