"""Tests for runtime composition and lazy clients."""

from unittest.mock import patch

from pydantic import SecretStr

from pixgen.config.models import Settings
from pixgen.runtime import build_runtime


def test_build_runtime_does_not_construct_clients_for_catalogue_commands() -> None:
    settings = Settings.model_construct(
        openai_api_key=SecretStr("openai-test"),
        gemini_api_key=SecretStr("gemini-test"),
    )

    with (
        patch("pixgen.runtime.load_settings", return_value=settings),
        patch("pixgen.runtime.httpx2.AsyncClient", autospec=True) as async_client,
    ):
        _, registry, _ = build_runtime()

    assert async_client.call_count == 0
    assert all(registry.provider_for(model.id).available for model in registry.models())
