"""Tests for providers.registry."""

import pytest

from pixgen.core.errors import PixgenError
from pixgen.providers.gemini import GEMINI_MODELS, GeminiProvider
from pixgen.providers.openai import OPENAI_MODELS, OpenAIProvider
from pixgen.providers.registry import ProviderRegistry


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_models_aggregates_all_providers(self) -> None:
        registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))
        models = registry.models()
        assert len(models) == len(OPENAI_MODELS) + len(GEMINI_MODELS)

    def test_provider_for_openai_model(self) -> None:
        openai = OpenAIProvider(None)
        registry = ProviderRegistry((openai, GeminiProvider(None)))
        provider = registry.provider_for("openai/gpt-image-2")
        assert provider is openai

    def test_provider_for_gemini_model(self) -> None:
        gemini = GeminiProvider(None)
        registry = ProviderRegistry((OpenAIProvider(None), gemini))
        provider = registry.provider_for("gemini/gemini-3.1-flash-image")
        assert provider is gemini

    def test_provider_for_unknown_model_raises(self) -> None:
        registry = ProviderRegistry((OpenAIProvider(None),))
        with pytest.raises(PixgenError, match="not in the curated catalog"):
            registry.provider_for("unknown/model")

    def test_get_model_returns_spec(self) -> None:
        registry = ProviderRegistry((OpenAIProvider(None),))
        spec = registry.get_model("openai/gpt-image-2")
        assert spec.id == "openai/gpt-image-2"
        assert spec.display_name == "GPT Image 2"

    def test_get_model_unknown_raises(self) -> None:
        registry = ProviderRegistry((OpenAIProvider(None),))
        with pytest.raises(PixgenError, match="not in the curated catalog"):
            registry.get_model("unknown/model")
