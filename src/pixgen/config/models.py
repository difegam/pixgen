"""Define application settings and configuration models."""

import os
import tomllib
from pathlib import Path

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
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
    "ModelGroup",
    "Settings",
    "load_settings",
]


class ModelGroup(BaseModel):
    """Define a named create-only group of image models."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    models: tuple[ModelId, ...] = Field(
        min_length=1,
        description="Ordered models selected by the group",
    )
    description: str = Field(min_length=1, description="Presentation description for the group")
    tags: tuple[str, ...] = Field(default=(), description="Presentation tags for the group")

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, tags: tuple[str, ...]) -> tuple[str, ...]:
        if any(not tag or tag != tag.strip() for tag in tags):
            raise ValueError("tags must be non-empty and must not have leading or trailing spaces")
        return tags

    @model_validator(mode="after")
    def _validate_group(self) -> ModelGroup:
        if not self.description.strip():
            raise ValueError("description must contain a non-whitespace character")
        if len(self.models) != len(set(self.models)):
            raise ValueError("models must not contain duplicate model IDs")
        return self


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
        env_file=".env",
        extra="forbid",
        frozen=True,
    )

    defaults: Defaults = Field(default_factory=Defaults)
    groups: dict[str, ModelGroup] = Field(
        default_factory=dict,
        description="Named create-only model groups",
    )
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PIXGEN_OPENAI_API_KEY", "OPENAI_API_KEY"),
        description="OpenAI API key",
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PIXGEN_GEMINI_API_KEY", "GEMINI_API_KEY"),
        description="Gemini API key",
    )

    @model_validator(mode="after")
    def _validate_group_names(self) -> Settings:
        if any(not name for name in self.groups):
            raise ValueError("group names must not be empty")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del file_secret_settings
        config_path = resolve_config_path()
        toml_source = TomlConfigSettingsSource(settings_cls, toml_file=config_path)
        return (init_settings, env_settings, dotenv_settings, toml_source)

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
    except (OSError, tomllib.TOMLDecodeError, ValidationError, ValueError) as exc:
        raise PixgenError(ErrorCode.INVALID_CONFIGURATION, str(exc)) from exc
