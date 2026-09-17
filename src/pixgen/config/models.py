from pathlib import Path

from pydantic import BaseModel, BaseSettings, SettingsConfigDict


class Defaults(BaseModel):
    image_model: str | None = None
    video_model: str | None = None


class GenerationSettings(BaseModel):
    output_dir: Path = Path.cwd()
    wait_timeout: float = 600
    wait_interval: float = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIXGEN_", env_nested_delimiter="__")

    defaults: Defaults = Defaults()
    generation: GenerationSettings = GenerationSettings()
    providers: dict[str, dict] = {}
