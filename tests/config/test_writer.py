"""Tests for configuration group persistence."""

from typing import TYPE_CHECKING

import pytest

from pixgen.config.models import ModelGroup
from pixgen.config.writer import ConfigRepository
from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from pathlib import Path


def _group() -> ModelGroup:
    return ModelGroup(
        models=("openai/gpt-image-2", "gemini/gemini-3.1-flash-image"),
        description="Models for product images",
        tags=("product", "marketing"),
    )


class TestConfigRepository:
    """Tests for ConfigRepository."""

    def test_creates_parent_directory_and_group(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config" / "pixgen.toml"

        ConfigRepository(config_path).create_group("product-hero", _group())

        assert config_path.exists()
        text = config_path.read_text()
        assert "[groups.product-hero]" in text
        assert 'description = "Models for product images"' in text

    def test_create_group_preserves_existing_settings(self, tmp_path: Path) -> None:
        config_path = tmp_path / "pixgen.toml"
        config_path.write_text(
            """[defaults]
image_create_models = ["openai/gpt-image-2"]
image_edit_models = ["gemini/gemini-3.1-flash-image"]

[generation]
max_parallel_requests = 9
max_variants = 3
max_jobs = 8
request_timeout_seconds = 120
run_timeout_seconds = 600

[groups.existing]
description = "Existing group"
tags = ["legacy"]
models = ["openai/gpt-image-2"]
"""
        )

        ConfigRepository(config_path).create_group("product-hero", _group())

        text = config_path.read_text()
        assert "max_parallel_requests = 9" in text
        assert "run_timeout_seconds = 600" in text
        assert "[groups.existing]" in text
        assert "[groups.product-hero]" in text

    def test_serialises_group_fields_in_order(self, tmp_path: Path) -> None:
        config_path = tmp_path / "pixgen.toml"

        ConfigRepository(config_path).create_group("product-hero", _group())

        text = config_path.read_text()
        group_text = text[text.index("[groups.product-hero]") :]
        description_index = group_text.index("description =")
        tags_index = group_text.index("tags =")
        models_index = group_text.index("models =")
        assert description_index < tags_index < models_index
        assert '"openai/gpt-image-2"' in text
        assert '"gemini/gemini-3.1-flash-image"' in text

    def test_create_group_rejects_existing_name_without_writing(self, tmp_path: Path) -> None:
        config_path = tmp_path / "pixgen.toml"
        original = """[groups.product-hero]
description = "Original"
tags = []
models = ["openai/gpt-image-2"]
"""
        config_path.write_text(original)

        with pytest.raises(PixgenError) as exc_info:
            ConfigRepository(config_path).create_group("product-hero", _group())

        assert exc_info.value.code is ErrorCode.INVALID_REQUEST
        assert config_path.read_text() == original

    def test_rejects_malformed_existing_toml_without_writing(self, tmp_path: Path) -> None:
        config_path = tmp_path / "pixgen.toml"
        original = "[groups\n"
        config_path.write_text(original)

        with pytest.raises(PixgenError) as exc_info:
            ConfigRepository(config_path).create_group("product-hero", _group())

        assert exc_info.value.code is ErrorCode.INVALID_CONFIGURATION
        assert config_path.read_text() == original

    def test_write_failure_does_not_publish_partial_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path = tmp_path / "pixgen.toml"
        monkeypatch.setattr(
            "pixgen.config.writer.write_atomic",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
        )

        with pytest.raises(PixgenError) as exc_info:
            ConfigRepository(config_path).create_group("product-hero", _group())

        assert exc_info.value.code is ErrorCode.INVALID_CONFIGURATION
        assert not config_path.exists()

    def test_serialised_output_excludes_credentials(self, tmp_path: Path) -> None:
        config_path = tmp_path / "pixgen.toml"

        ConfigRepository(config_path).create_group("product-hero", _group())

        text = config_path.read_text()
        assert "api_key" not in text
        assert "OPENAI_API_KEY" not in text
        assert "GEMINI_API_KEY" not in text
