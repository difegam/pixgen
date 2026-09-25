"""Composition root for settings, clients, adapters, and application."""

from __future__ import annotations

import httpx2

from pixgen.application import ImageApplication
from pixgen.config.models import Settings, load_settings
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.registry import ProviderRegistry

__all__: list[str] = [
    "build_runtime",
]


def build_runtime() -> tuple[ImageApplication, ProviderRegistry, Settings]:
    """Construct settings, provider clients, registry, and application."""
    settings = load_settings()

    openai_client = None
    if settings.openai_api_key:
        openai_client = httpx2.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
            },
            timeout=httpx2.Timeout(settings.generation.request_timeout_seconds),
        )

    gemini_client = None
    if settings.gemini_api_key:
        from google.genai import Client
        from google.genai.types import HttpOptions, HttpRetryOptions

        gemini_client = Client(
            api_key=settings.gemini_api_key.get_secret_value(),
            http_options=HttpOptions(
                timeout=settings.generation.request_timeout_seconds * 1000,
                retry_options=HttpRetryOptions(attempts=1),
            ),
        )

    openai_provider = OpenAIProvider(openai_client)
    gemini_provider = GeminiProvider(gemini_client)
    registry = ProviderRegistry((openai_provider, gemini_provider))
    application = ImageApplication(registry, settings)

    return application, registry, settings
