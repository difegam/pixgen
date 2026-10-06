"""Build the info command."""

import importlib.metadata
import os
import platform
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter
from pydantic import AliasChoices
from rich.console import Console
from rich.text import Text

from pixgen.config.models import Settings
from pixgen.config.paths import resolve_config_path, resolve_env_file_path
from pixgen.core.versioning import ReleaseInfo, UpdateStatus, compare_versions
from pixgen.releases import fetch_latest_release

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__: list[str] = [
    "ReleaseChecker",
    "build_info_command",
]

type ReleaseChecker = Callable[[], ReleaseInfo | None]

_SECRET_FIELDS: tuple[str, ...] = ("openai_api_key", "gemini_api_key")
_VISIBLE_SUFFIX_LEN = 4
_MAX_MASK_LEN = 8
_MASK_CHAR = "*"


def _secret_env_names() -> tuple[str, ...]:
    """Return every environment variable name Settings accepts for provider keys."""
    names: list[str] = []
    for field_name in _SECRET_FIELDS:
        alias = Settings.model_fields[field_name].validation_alias
        if isinstance(alias, AliasChoices):
            names.extend(choice for choice in alias.choices if isinstance(choice, str))
        elif isinstance(alias, str):
            names.append(alias)
    return tuple(names)


_SECRET_ENV_VARS: frozenset[str] = frozenset(_secret_env_names())
_ENV_VARS: tuple[str, ...] = ("PIXGEN_CONFIG", *_secret_env_names())


def _installed_version() -> str:
    try:
        return importlib.metadata.version("pixgen")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _heading(console: Console, title: str) -> None:
    console.print(Text(f"{title}:", style="bold cyan"))


def _row(console: Console, label: str, value: Text | str) -> None:
    line = Text(f"{label}: ", style="bold")
    line.append(value if isinstance(value, Text) else Text(value))
    console.print(line, soft_wrap=True)


def _path_value(path: Path) -> Text:
    marker = Text(" (found)", style="green") if path.is_file() else Text(" (missing)", style="dim")
    return Text(str(path), style="blue") + marker


def _mask_secret(value: str) -> Text:
    """Mask a secret, revealing only a short suffix when the value is long enough."""
    if len(value) <= 2 * _VISIBLE_SUFFIX_LEN:
        return Text(_MASK_CHAR * len(value), style="dim yellow")
    mask = _MASK_CHAR * min(len(value) - _VISIBLE_SUFFIX_LEN, _MAX_MASK_LEN)
    return Text.assemble(
        (mask, "dim yellow"),
        (value[-_VISIBLE_SUFFIX_LEN:], "bold green"),
    )


def _env_value(name: str) -> Text:
    value = os.environ.get(name)
    if not value:
        return Text("not set", style="dim")
    if name in _SECRET_ENV_VARS:
        return _mask_secret(value)
    return Text(value, style="blue")


def _update_line(current: str, release: ReleaseInfo | None) -> Text:
    if release is None:
        return Text("could not check for updates", style="dim")
    match compare_versions(current, release.tag):
        case UpdateStatus.UPDATE_AVAILABLE:
            line = Text(f"update available: {release.tag}", style="bold yellow")
            line.append(f" ({release.url})", style="dim")
            return line
        case UpdateStatus.UP_TO_DATE:
            return Text("up to date", style="green")
        case UpdateStatus.AHEAD:
            return Text(f"ahead of latest release {release.tag}", style="magenta")
        case UpdateStatus.UNKNOWN:
            return Text(f"could not compare with {release.tag}", style="dim")


def build_info_command(
    release_checker: ReleaseChecker | None = None,
) -> Callable[..., None]:
    """Build the info command function."""
    checker = release_checker or fetch_latest_release

    def info(
        *,
        check: Annotated[bool, Parameter(negative="--no-check")] = True,
    ) -> None:
        """Show configuration paths, environment and version information.

        Args:
            check: Look up the latest release to report whether an update is available.
        """
        console = Console(highlight=False)
        current = _installed_version()

        _heading(console, "Version info")
        _row(console, "version", Text(current, style="bold green"))
        _row(console, "python", platform.python_version())
        _row(console, "platform", platform.platform())
        if check:
            _row(console, "update", _update_line(current, checker()))
        console.print()

        _heading(console, "Config files")
        _row(console, "config", _path_value(resolve_config_path()))
        _row(console, "env file", _path_value(resolve_env_file_path()))
        console.print()

        _heading(console, "Env vars")
        for name in _ENV_VARS:
            _row(console, name, _env_value(name))

    return info
