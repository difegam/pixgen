"""Tests for config.models."""

from typing import TYPE_CHECKING

import pytest

from pixgen.config.models import Defaults, GenerationSettings, ModelGroup, Settings, load_settings
from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from pathlib import Path


class TestDefaults:
    """Tests for Defaults model."""

    def test_default_models(self) -> None:
        defaults = Defaults()
        assert defaults.image_create_models == ("openai/gpt-image-2",)
        assert defaults.image_edit_models == ("openai/gpt-image-2",)

    def test_custom_models(self) -> None:
        defaults = Defaults(
            image_create_models=("gemini/gemini-3.1-flash-image",),
            image_edit_models=("openai/gpt-image-2", "gemini/gemini-3.1-flash-image"),
        )
        assert len(defaults.image_edit_models) == 2


class TestModelGroup:
    """Tests for model group configuration."""

    def test_model_group_accepts_models_description_and_tags(self) -> None:
        group = ModelGroup(
            models=["openai/gpt-image-2", "gemini/gemini-3.1-flash-image"],
            description="Models for product images",
            tags=["product", "marketing"],
        )

        assert group.models == ("openai/gpt-image-2", "gemini/gemini-3.1-flash-image")
        assert group.description == "Models for product images"
        assert group.tags == ("product", "marketing")

    def test_model_group_defaults_tags_to_empty(self) -> None:
        group = ModelGroup(
            models=["openai/gpt-image-2"],
            description="Models for product images",
        )

        assert group.tags == ()

    def test_model_group_rejects_empty_models(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            ModelGroup(models=[], description="Models for product images")

    def test_model_group_rejects_duplicate_models(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            ModelGroup(
                models=["openai/gpt-image-2", "openai/gpt-image-2"],
                description="Models for product images",
            )

    def test_model_group_rejects_blank_description(self) -> None:
        with pytest.raises(ValueError, match="description"):
            ModelGroup(models=["openai/gpt-image-2"], description="   ")

    @pytest.mark.parametrize(
        "tag",
        ["", "   ", " marketing", "marketing "],
        ids=["empty", "blank", "leading-space", "trailing-space"],
    )
    def test_model_group_rejects_blank_or_padded_tags(self, tag: str) -> None:
        with pytest.raises(ValueError, match="tag"):
            ModelGroup(models=["openai/gpt-image-2"], description="Models", tags=[tag])


class TestGenerationSettings:
    """Tests for GenerationSettings model."""

    def test_defaults(self) -> None:
        settings = GenerationSettings()
        assert settings.output_dir is None
        assert settings.max_parallel_requests == 4
        assert settings.max_variants == 10
        assert settings.max_jobs == 10
        assert settings.request_timeout_seconds == 300
        assert settings.run_timeout_seconds is None

    def test_custom_values(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        settings = GenerationSettings(
            output_dir=output_dir,
            max_parallel_requests=8,
            max_variants=5,
            max_jobs=20,
            request_timeout_seconds=600,
            run_timeout_seconds=120,
        )
        assert settings.output_dir == output_dir
        assert settings.max_parallel_requests == 8


class TestSettings:
    """Tests for Settings model."""

    def test_defaults_without_config_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("PIXGEN_CONFIG", raising=False)
        monkeypatch.setattr("pixgen.config.models.resolve_config_path", lambda: tmp_path / "x.toml")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("PIXGEN_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PIXGEN_GEMINI_API_KEY", raising=False)
        settings = Settings(_env_file=None)
        assert settings.defaults.image_create_models == ("openai/gpt-image-2",)
        assert settings.groups == {}
        assert settings.openai_api_key is None
        assert settings.gemini_api_key is None

    def test_env_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PIXGEN_CONFIG", raising=False)
        monkeypatch.delenv("PIXGEN_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PIXGEN_GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
        settings = Settings()
        assert settings.openai_api_key is not None
        assert settings.openai_api_key.get_secret_value() == "sk-test-key"
        assert settings.gemini_api_key is not None
        assert settings.gemini_api_key.get_secret_value() == "gemini-test-key"

    def test_pixgen_config_relative_path_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PIXGEN_CONFIG", "relative/path.toml")
        with pytest.raises(ValueError, match="must be an absolute path"):
            Settings()

    def test_pixgen_config_missing_file_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.toml"
        monkeypatch.setenv("PIXGEN_CONFIG", str(missing))
        with pytest.raises(PixgenError, match="file not found"):
            load_settings()

    def test_pixgen_config_missing_file_allowed_when_not_required(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PIXGEN_CONFIG", str(tmp_path / "new.toml"))
        monkeypatch.delenv("PIXGEN_GENERATION__OUTPUT_DIR", raising=False)

        settings = load_settings(require_config_file=False)

        assert settings.groups == {}

    def test_pixgen_config_valid_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[defaults]\nimage_create_models = ["gemini/gemini-3.1-flash-image"]\n'
        )
        monkeypatch.setenv("PIXGEN_CONFIG", str(config_file))
        settings = Settings()
        assert settings.defaults.image_create_models == ("gemini/gemini-3.1-flash-image",)

    def test_settings_loads_groups_from_toml(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[groups.product-hero]
description = "Models for product images"
tags = ["product", "marketing"]
models = ["openai/gpt-image-2", "gemini/gemini-3.1-flash-image"]
"""
        )
        monkeypatch.setenv("PIXGEN_CONFIG", str(config_file))

        settings = Settings()

        assert settings.groups["product-hero"].models == (
            "openai/gpt-image-2",
            "gemini/gemini-3.1-flash-image",
        )
        assert settings.groups["product-hero"].description == "Models for product images"
        assert settings.groups["product-hero"].tags == ("product", "marketing")

    def test_settings_rejects_unknown_group_fields(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[groups.product-hero]
description = "Models for product images"
models = ["openai/gpt-image-2"]
unexpected = true
"""
        )
        monkeypatch.setenv("PIXGEN_CONFIG", str(config_file))

        with pytest.raises(PixgenError) as exc_info:
            load_settings()

        assert exc_info.value.code is ErrorCode.INVALID_CONFIGURATION

    def test_settings_rejects_empty_group_name(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[groups.""]
description = "Models for product images"
models = ["openai/gpt-image-2"]
"""
        )
        monkeypatch.setenv("PIXGEN_CONFIG", str(config_file))

        with pytest.raises(PixgenError) as exc_info:
            load_settings()

        assert exc_info.value.code is ErrorCode.INVALID_CONFIGURATION


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_load_settings_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PIXGEN_CONFIG", raising=False)
        settings = load_settings()
        assert isinstance(settings, Settings)

    def test_load_settings_invalid_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PIXGEN_CONFIG", "relative/path.toml")
        with pytest.raises(PixgenError, match="must be an absolute path"):
            load_settings()
