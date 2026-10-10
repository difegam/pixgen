"""Provider-native Cyclopts commands built from provider params and catalogues."""

from pixgen.cli.providers.gemini import GeminiCliFactory
from pixgen.cli.providers.openai import OpenAICliFactory
from pixgen.cli.providers.openrouter import OpenRouterCliFactory

__all__: list[str] = ["PROVIDER_CLIS"]

PROVIDER_CLIS = (OpenAICliFactory(), GeminiCliFactory(), OpenRouterCliFactory())
