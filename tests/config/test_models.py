"""Tests for config.models."""

from pathlib import Path

import pytest

from pixgen.config.models import Defaults, GenerationSettings, Settings, load_settings
from pixgen.core.errors import PixgenError


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

    def test_custom_values(self) -> None:
        settings = GenerationSettings(
            output_dir=Path("/tmp/output"),  # noqa: S108
            max_parallel_requests=8,
            max_variants=5,
            max_jobs=20,
            request_timeout_seconds=600,
            run_timeout_seconds=120,
        )
        assert settings.output_dir == Path("/tmp/output")  # noqa: S108
        assert settings.max_parallel_requests == 8


class TestSettings:
    """Tests for Settings model."""

    def test_defaults_without_config_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PIXGEN_CONFIG", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("PIXGEN_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PIXGEN_GEMINI_API_KEY", raising=False)
        settings = Settings(_env_file=None)
        assert settings.defaults.image_create_models == ("openai/gpt-image-2",)
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
            Settings()

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


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_load_settings_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PIXGEN_CONFIG", raising=False)
        settings = load_settings()
        assert isinstance(settings, Settings)

    def test_load_settings_invalid_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PIXGEN_CONFIG", "relative/path.toml")
        with pytest.raises((PixgenError, ValueError), match="must be an absolute path"):
            load_settings()
