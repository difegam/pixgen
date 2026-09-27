from typing import TYPE_CHECKING

import httpx2

from pixgen.application import ImageApplication
from pixgen.config.models import Settings, load_settings
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

    from google.genai import Client
    from pydantic import SecretStr

__all__: list[str] = [
    "build_runtime",
]


def get_open_ai_factory(
    openai_api_key: SecretStr | None,
    request_timeout_seconds: int,
) -> Callable[[], httpx2.AsyncClient] | None:
    if not openai_api_key:
        return None

    def make_openai_client() -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {openai_api_key.get_secret_value()}"},
            timeout=httpx2.Timeout(request_timeout_seconds),
        )

    return make_openai_client


def get_gemini_factory(
    gemini_api_key: SecretStr | None,
    request_timeout_seconds: int,
) -> Callable[[], Client] | None:
    if not gemini_api_key:
        return None

    def make_gemini_client() -> Client:
        from google.genai import Client
        from google.genai.types import HttpOptions, HttpRetryOptions

        return Client(
            api_key=gemini_api_key.get_secret_value(),
            http_options=HttpOptions(
                timeout=request_timeout_seconds * 1000,
                retry_options=HttpRetryOptions(attempts=1),
            ),
        )

    return make_gemini_client


def build_runtime() -> tuple[ImageApplication, ProviderRegistry, Settings]:
    """Construct settings, provider clients, registry, and application."""
    settings = load_settings()

    # OpenAI client factory - lazy initialization
    openai_factory = get_open_ai_factory(
        settings.openai_api_key,
        settings.generation.request_timeout_seconds,
    )

    # Gemini client factory - lazy initialization
    gemini_factory = get_gemini_factory(
        settings.gemini_api_key,
        settings.generation.request_timeout_seconds,
    )

    openai_provider = OpenAIProvider(None, client_factory=openai_factory)
    gemini_provider = GeminiProvider(None, client_factory=gemini_factory)
    registry = ProviderRegistry((openai_provider, gemini_provider))
    application = ImageApplication(registry, settings)

    return application, registry, settings
