import tomllib
from typing import TYPE_CHECKING

from pixgen.config.models import Settings

if TYPE_CHECKING:
    from pathlib import Path


def read_config_file(path: Path | None = None) -> Settings:
    if not path:
        return Settings()

    with path.open("rb") as config_file:
        config = tomllib.load(config_file)
        return Settings.model_validate(config)
