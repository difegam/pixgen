"""Tests for runtime composition and lazy clients."""

from unittest.mock import patch

from pydantic import SecretStr

from pixgen.config.models import Settings
from pixgen.runtime import build_runtime


def test_build_runtime_does_not_construct_clients_for_catalogue_commands() -> None:
    settings = Settings.model_construct(
        openai_api_key=SecretStr("openai-test"),
        gemini_api_key=SecretStr("gemini-test"),
        openrouter_api_key=SecretStr("openrouter-test"),
    )

    with (
        patch("pixgen.runtime.load_settings", return_value=settings),
        patch("pixgen.providers.http.httpx2.AsyncClient", autospec=True) as async_client,
    ):
        runtime = build_runtime()

    assert async_client.call_count == 0
    assert all(
        runtime.registry.provider_for(model.id).available for model in runtime.registry.models()
    )
    assert tuple(factory.name for factory in runtime.cli_factories) == (
        "openai",
        "gemini",
        "openrouter",
    )
    openrouter = runtime.registry.provider_for("openrouter/google/gemini-3.1-flash-image")
    assert openrouter.available is True


def test_build_runtime_keeps_openrouter_catalogue_available_without_credentials() -> None:
    settings = Settings.model_construct(
        openai_api_key=None,
        gemini_api_key=None,
        openrouter_api_key=None,
    )

    with patch("pixgen.runtime.load_settings", return_value=settings):
        runtime = build_runtime()

    assert "openrouter/google/gemini-3.1-flash-image" in {
        model.id for model in runtime.registry.models()
    }
    assert (
        runtime.registry.provider_for("openrouter/google/gemini-3.1-flash-image").available is False
    )


def test_build_runtime_composes_group_repository_for_resolved_config_path(
    monkeypatch, tmp_path
) -> None:
    config_path = tmp_path / "pixgen.toml"
    monkeypatch.setenv("PIXGEN_CONFIG", str(config_path))
    settings = Settings.model_construct()

    with patch("pixgen.runtime.load_settings", return_value=settings):
        runtime = build_runtime()

    assert runtime.group_repository.path == config_path
