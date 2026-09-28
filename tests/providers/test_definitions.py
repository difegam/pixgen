"""Tests for provider-owned model definitions."""

import pytest

from pixgen.core.models import ImageOperation
from pixgen.core.parameters import SharedImageParams
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.openai import OpenAIProvider


class TestOpenAIDefinitions:
    """Test OpenAI ratio mappings."""

    @pytest.mark.parametrize("operation", list(ImageOperation))
    def test_gpt_image_two_maps_wide_ratio(self, operation: ImageOperation) -> None:
        provider = OpenAIProvider(None)
        definition = next(
            item for item in provider.definitions() if item.spec.id == "openai/gpt-image-2"
        )
        params = definition.operations[operation].resolve(SharedImageParams(aspect_ratio="16:9"))
        assert params.size == "1536x864"

    def test_mini_rejects_unmapped_wide_ratio(self) -> None:
        provider = OpenAIProvider(None)
        definition = next(
            item for item in provider.definitions() if item.spec.id == "openai/gpt-image-1-mini"
        )
        with pytest.raises(ValueError, match="unsupported aspect ratio"):
            definition.operations[ImageOperation.IMAGE_CREATE].resolve(
                SharedImageParams(aspect_ratio="16:9")
            )

    def test_omitted_ratio_keeps_size_default(self) -> None:
        provider = OpenAIProvider(None)
        definition = next(
            item for item in provider.definitions() if item.spec.id == "openai/gpt-image-2"
        )
        assert (
            definition.operations[ImageOperation.IMAGE_CREATE].resolve(SharedImageParams()).size
            is None
        )

    def test_resolves_shared_parameters_through_provider_contract(self) -> None:
        provider = OpenAIProvider(None)

        assert provider.resolve_shared_parameters(
            "openai/gpt-image-2",
            ImageOperation.IMAGE_CREATE,
            SharedImageParams(aspect_ratio="16:9"),
        ) == {"size": "1536x864"}


class TestGeminiDefinitions:
    """Test Gemini ratio mappings."""

    @pytest.mark.parametrize("operation", list(ImageOperation))
    def test_canonical_wide_ratio_uses_native_spelling(self, operation: ImageOperation) -> None:
        provider = GeminiProvider(None)
        definition = next(
            item
            for item in provider.definitions()
            if item.spec.id == "gemini/gemini-3.1-flash-image"
        )
        params = definition.operations[operation].resolve(SharedImageParams(aspect_ratio="21:9"))
        assert params.aspect_ratio == "21:9"

    def test_lite_defaults_to_one_k(self) -> None:
        provider = GeminiProvider(None)
        definition = next(
            item
            for item in provider.definitions()
            if item.spec.id == "gemini/gemini-3.1-flash-lite-image"
        )
        assert definition.operations[ImageOperation.IMAGE_CREATE].defaults.image_size is None

    def test_lists_shared_ratios_through_provider_contract(self) -> None:
        provider = GeminiProvider(None)

        assert "7:3" in provider.shared_aspect_ratios(
            "gemini/gemini-3.1-flash-image",
            ImageOperation.IMAGE_CREATE,
        )
