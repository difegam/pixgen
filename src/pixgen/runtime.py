"""Compose command applications and lazy provider clients."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pixgen.application import ImageApplication
from pixgen.config.models import Settings, load_settings
from pixgen.config.paths import resolve_config_path
from pixgen.config.writer import ConfigRepository
from pixgen.optimization.application import OptimizeApplication
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.http import make_http_client_factory
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.openrouter import OpenRouterProvider
from pixgen.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx2
    from google.genai import Client
    from pydantic import SecretStr


__all__: list[str] = [
    "Runtime",
    "build_runtime",
]


@dataclass(frozen=True, slots=True)
class Runtime:
    """Hold application dependencies assembled for one CLI invocation."""

    application: ImageApplication
    optimize_application: OptimizeApplication
    registry: ProviderRegistry
    settings: Settings
    group_repository: ConfigRepository


def get_open_ai_factory(
    openai_api_key: SecretStr | None,
    request_timeout_seconds: int,
) -> Callable[[], httpx2.AsyncClient] | None:
    return make_http_client_factory(
        openai_api_key,
        base_url="https://api.openai.com/v1",
        request_timeout_seconds=request_timeout_seconds,
    )


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


def build_runtime(*, require_config_file: bool = True) -> Runtime:
    """Construct settings, provider clients, registry, and application."""
    settings = load_settings(require_config_file=require_config_file)

    # OpenAI client factory - lazy initialization
    openai_factory = get_open_ai_factory(
        settings.openai_api_key,
        settings.generation.request_timeout_seconds,
    )

    # OpenRouter client factory - lazy initialization
    openrouter_factory = make_http_client_factory(
        settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        request_timeout_seconds=settings.generation.request_timeout_seconds,
    )

    # Gemini client factory - lazy initialization
    gemini_factory = get_gemini_factory(
        settings.gemini_api_key,
        settings.generation.request_timeout_seconds,
    )

    openai_provider = OpenAIProvider(None, client_factory=openai_factory)
    gemini_provider = GeminiProvider(None, client_factory=gemini_factory)
    openrouter_provider = OpenRouterProvider(None, client_factory=openrouter_factory)
    registry = ProviderRegistry((openai_provider, gemini_provider, openrouter_provider))
    application = ImageApplication(registry, settings)

    return Runtime(
        application=application,
        optimize_application=OptimizeApplication(settings),
        registry=registry,
        settings=settings,
        group_repository=ConfigRepository(resolve_config_path()),
    )
