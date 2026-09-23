from pathlib import Path

from pydantic import BaseModel, Field, PositiveFloat
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from pixgen.config.paths import resolve_config_path
from pixgen.core.models import ModelId  # noqa: TC001


class Defaults(BaseModel):
    image_model: ModelId | None = Field(
        default="google/gemini-3.1-flash-image",
        description="The default image generation model",
    )
    video_model: ModelId | None = Field(
        default="google/gemini-omni-1.1-flash",
        description="The default video generation model",
    )


class GenerationSettings(BaseModel):
    output_dir: Path | None = Field(default_factory=Path.cwd)
    wait_timeout: PositiveFloat = Field(default=600.0)
    wait_interval: PositiveFloat = Field(default=3.0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PIXGEN_",
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
        toml_file=resolve_config_path(),
    )

    defaults: Defaults = Field(default_factory=Defaults)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del dotenv_settings, file_secret_settings
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls),
        )
