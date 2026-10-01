"""Write validated Pixgen configuration changes atomically."""

import json
import re
import tomllib
from pathlib import Path

from pydantic import ValidationError

from pixgen.artifacts import write_atomic
from pixgen.config.models import ModelGroup, Settings
from pixgen.core.errors import ErrorCode, PixgenError

__all__: list[str] = [
    "ConfigRepository",
]


class ConfigRepository:
    """Persist supported Pixgen configuration changes to one TOML file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Return the repository's configuration path."""
        return self._path

    def create_group(self, name: str, group: ModelGroup) -> None:
        """Create a new model group without replacing an existing group."""
        try:
            settings = self._load_settings()
            if name in settings.groups:
                raise PixgenError(ErrorCode.INVALID_REQUEST, f"model group already exists: {name}")
            updated = settings.model_copy(
                update={"groups": {**settings.groups, name: group}},
            )
            data = _serialise_settings(updated).encode()
            write_atomic(self._path, data, overwrite=True)
        except PixgenError:
            raise
        except (OSError, tomllib.TOMLDecodeError, ValidationError, ValueError) as exc:
            raise PixgenError(
                ErrorCode.INVALID_CONFIGURATION,
                f"cannot write configuration: {self._path}: {exc}",
            ) from exc

    def _load_settings(self) -> Settings:
        if not self._path.exists():
            return Settings.model_validate({})
        with self._path.open("rb") as file:
            raw = tomllib.load(file)
        return Settings.model_validate(raw)


def _serialise_settings(settings: Settings) -> str:
    lines: list[str] = []
    lines.extend(_serialise_table("defaults", settings.defaults.model_dump(mode="python")))
    lines.extend(_serialise_table("generation", settings.generation.model_dump(mode="python")))
    for name, group in settings.groups.items():
        lines.append("")
        lines.append(f"[groups.{_toml_key(name)}]")
        lines.extend(
            _serialise_fields(
                {
                    "description": group.description,
                    "tags": group.tags,
                    "models": group.models,
                }
            )
        )
    return "\n".join(lines) + "\n"


def _serialise_table(name: str, values: dict[str, object]) -> list[str]:
    lines = [f"[{name}]"]
    lines.extend(_serialise_fields(values))
    return lines


def _serialise_fields(values: dict[str, object]) -> list[str]:
    return [f"{key} = {_toml_value(value)}" for key, value in values.items() if value is not None]


def _toml_value(value: object) -> str:
    if isinstance(value, Path):
        return _toml_string(str(value))
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, tuple):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, (int, float, bool)):
        return str(value).lower() if isinstance(value, bool) else str(value)
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_key(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    return _toml_string(value)
