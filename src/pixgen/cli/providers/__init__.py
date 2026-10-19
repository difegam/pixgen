"""Provider-native Cyclopts commands built from provider params and catalogues."""

from pixgen.cli.providers.native import NativeCliFactory, NativeProviderSpec
from pixgen.cli.providers.openrouter import OPENROUTER_SPEC
from pixgen.providers.gemini import GeminiParams
from pixgen.providers.openai import OpenAIParams

__all__: list[str] = ["GEMINI_SPEC", "OPENAI_SPEC", "OPENROUTER_SPEC", "PROVIDER_CLIS"]

OPENAI_SPEC = NativeProviderSpec(
    name="openai",
    display_name="OpenAI",
    params_type=OpenAIParams,
    model_error="OpenAI native commands require an OpenAI model name",
)
GEMINI_SPEC = NativeProviderSpec(
    name="gemini",
    display_name="Gemini",
    params_type=GeminiParams,
    model_error="Gemini native commands require a Gemini model name",
)

PROVIDER_CLIS = (
    NativeCliFactory(OPENAI_SPEC),
    NativeCliFactory(GEMINI_SPEC),
    NativeCliFactory(OPENROUTER_SPEC),
)
