"""Write validated Pixgen configuration changes atomically."""

from typing import TYPE_CHECKING

import tomlkit
from pydantic import ValidationError
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table

from pixgen.artifacts import write_atomic
from pixgen.config.models import Defaults, GenerationSettings, ModelGroup
from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from pathlib import Path

    from tomlkit.toml_document import TOMLDocument

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
        document, groups = self._load_document()
        if name in groups:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"model group already exists: {name}. Use 'pixgen group edit {name}' to change it.",
            )
        try:
            _groups_table(document)[name] = _group_table(group)
            data = tomlkit.dumps(document).encode()
            write_atomic(self._path, data, overwrite=True)
        except (OSError, ValueError, TOMLKitError) as exc:
            raise PixgenError(
                ErrorCode.INVALID_CONFIGURATION,
                f"cannot write configuration: {self._path}: {exc}",
            ) from exc

    def list_groups(self) -> dict[str, ModelGroup]:
        """Return the configured model groups in file order."""
        return self._load_document()[1]

    def _load_document(self) -> tuple[TOMLDocument, dict[str, ModelGroup]]:
        try:
            text = self._path.read_text(encoding="utf-8") if self._path.exists() else ""
            document = tomlkit.parse(text)
            raw = document.unwrap()
            groups = raw.get("groups", {})
            if not isinstance(groups, dict):
                raise ValueError("groups must be a table")
            if any(not group_name for group_name in groups):
                raise ValueError("group names must not be empty")
            Defaults.model_validate(raw.get("defaults", {}))
            GenerationSettings.model_validate(raw.get("generation", {}))
            validated = {key: ModelGroup.model_validate(value) for key, value in groups.items()}
        except (OSError, TOMLKitError, ValidationError, ValueError) as exc:
            raise PixgenError(
                ErrorCode.INVALID_CONFIGURATION,
                f"cannot read configuration: {self._path}: {exc}",
            ) from exc
        return document, validated


def _groups_table(document: TOMLDocument) -> Table:
    """Return the standard ``[groups]`` table, creating it when absent."""
    if "groups" not in document:
        document["groups"] = tomlkit.table(is_super_table=True)
    groups = document["groups"]
    if not isinstance(groups, Table):
        raise ValueError("groups must be a standard table, not an inline table")
    return groups


def _group_table(group: ModelGroup) -> Table:
    table = tomlkit.table()
    table.add("description", group.description)
    table.add("tags", list(group.tags))
    table.add("models", list(group.models))
    return table
