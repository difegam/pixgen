"""Define application settings and configuration models."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from pixgen.config.paths import resolve_config_path
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.models import ModelId

__all__: list[str] = [
    "Defaults",
    "GenerationSettings",
    "Settings",
    "load_settings",
]


class Defaults(BaseModel):
    """Default model lists for operations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    image_create_models: tuple[ModelId, ...] = Field(
        default=("openai/gpt-image-2",),
        description="Default models for image create",
    )
    image_edit_models: tuple[ModelId, ...] = Field(
        default=("openai/gpt-image-2",),
        description="Default models for image edit",
    )


class GenerationSettings(BaseModel):
    """Generation execution settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    output_dir: Path | None = Field(
        default=None,
        description="Default output directory (None uses ./pixgen/)",
    )
    max_parallel_requests: int = Field(default=4, ge=1, description="Max concurrent requests")
    max_variants: int = Field(default=10, ge=1, description="Max variants per model")
    max_jobs: int = Field(default=10, ge=1, description="Max total jobs (models x variants)")
    request_timeout_seconds: int = Field(
        default=300, ge=1, description="Timeout per provider request"
    )
    run_timeout_seconds: int | None = Field(
        default=None, ge=1, description="Optional whole-run deadline"
    )


class Settings(BaseSettings):
    """Application settings loaded from TOML and environment."""

    model_config = SettingsConfigDict(
        env_prefix="PIXGEN_",
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
    )

    defaults: Defaults = Field(default_factory=Defaults)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        description="OpenAI API key",
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="GEMINI_API_KEY",
        description="Gemini API key",
    )

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
        config_path = resolve_config_path()
        toml_source = TomlConfigSettingsSource(settings_cls, toml_file=config_path)
        return (init_settings, env_settings, toml_source)

    @model_validator(mode="after")
    def _validate_toml_file(self) -> Settings:
        config_path = resolve_config_path()
        env_path = os.environ.get("PIXGEN_CONFIG")
        if env_path and not config_path.is_file():
            raise PixgenError(
                ErrorCode.INVALID_CONFIGURATION,
                f"PIXGEN_CONFIG file not found: {config_path}",
            )
        return self


def load_settings() -> Settings:
    """Load settings, mapping validation errors to PixgenError."""
    try:
        return Settings()
    except ValidationError as exc:
        raise PixgenError(ErrorCode.INVALID_CONFIGURATION, str(exc)) from exc
