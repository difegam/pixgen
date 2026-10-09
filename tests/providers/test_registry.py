"""Tests for providers.registry."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.models import ImageOperation
from pixgen.core.parameters import ProviderParams, SharedImageParams
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent
from pixgen.providers.base import ProviderImage
from pixgen.providers.gemini import GEMINI_MODELS, GeminiProvider
from pixgen.providers.openai import OPENAI_MODELS, OpenAIProvider
from pixgen.providers.openrouter import OpenRouterProvider
from pixgen.providers.registry import ProviderRegistry
from tests.factories import make_model_definition, make_model_spec

if TYPE_CHECKING:
    from pixgen.core.definitions import ModelDefinition


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

    def test_provider_for_nested_openrouter_model(self) -> None:
        openrouter = OpenRouterProvider(None)
        registry = ProviderRegistry((openrouter,))

        assert registry.provider_for("openrouter/google/gemini-3.1-flash-image") is openrouter

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

    def test_providers_returns_registered_order(self) -> None:
        openai = OpenAIProvider(None)
        gemini = GeminiProvider(None)
        registry = ProviderRegistry((openai, gemini))

        assert registry.providers() == (openai, gemini)

    def test_rejects_duplicate_provider_names(self) -> None:
        with pytest.raises(ValueError, match="duplicate provider name"):
            ProviderRegistry((OpenAIProvider(None), OpenAIProvider(None)))

    def test_rejects_model_owned_by_another_provider(self) -> None:
        provider = OpenAIProvider(None)
        provider.name = "gemini"
        with pytest.raises(ValueError, match="not owned by provider"):
            ProviderRegistry((provider,))

    def test_shared_aspect_ratios_are_projected_from_provider_definitions(self) -> None:
        registry = ProviderRegistry((OpenAIProvider(None),))

        assert "16:9" in registry.shared_aspect_ratios(
            "openai/gpt-image-2", ImageOperation.IMAGE_CREATE
        )


class CatalogueOnlyProvider:
    """Provider exposing only the narrowed generation protocol."""

    name = "fake"

    def __init__(self, *definitions: ModelDefinition) -> None:
        self.catalogue = definitions

    @property
    def available(self) -> bool:
        return True

    def declared_media_type(self, _request: object) -> None:
        return None

    async def generate(self, _request: object) -> ProviderImage:
        return ProviderImage(b"png", "image/png")


class RatioParams(ProviderParams):
    """Native parameters with one ratio-controlled field."""

    size: str | None = None


def _fake_registry() -> ProviderRegistry:
    create_only = make_model_spec(
        model_id="fake/create-only", operations=frozenset({ImageOperation.IMAGE_CREATE})
    )
    return ProviderRegistry(
        (
            CatalogueOnlyProvider(
                make_model_definition(
                    spec=make_model_spec(model_id="fake/model"),
                    parameter_type=RatioParams,
                    aspect_ratios={"16:9": {"size": "wide"}, "1:1": {"size": "square"}},
                ),
                make_model_definition(spec=create_only),
            ),
        )
    )


class TestRegistryCatalogue:
    """The registry answers catalogue questions from provider definitions."""

    def test_accepts_provider_with_only_generation_protocol(self) -> None:
        registry = _fake_registry()
        assert [spec.id for spec in registry.models()] == ["fake/model", "fake/create-only"]
        assert isinstance(registry.provider_for("fake/model"), CatalogueOnlyProvider)

    def test_parameter_schema_reads_definition(self) -> None:
        schema = _fake_registry().parameter_schema("fake/model", ImageOperation.IMAGE_CREATE)
        assert schema == RatioParams.model_json_schema()

    def test_shared_aspect_ratios_read_definition(self) -> None:
        ratios = _fake_registry().shared_aspect_ratios("fake/model", ImageOperation.IMAGE_EDIT)
        assert ratios == ("16:9", "1:1")

    def test_validate_resolves_shared_ratio(self) -> None:
        request = _fake_registry().validate(
            intent=ImageCreateIntent(prompt="test"),
            model_id="fake/model",
            parameters=SharedImageParams(aspect_ratio="16:9"),
        )
        assert request.model.id == "fake/model"
        assert request.parameters == RatioParams(size="wide")

    def test_validate_rejects_unsupported_operation(self) -> None:
        with pytest.raises(PixgenError, match="does not support image-edit") as exc_info:
            _fake_registry().validate(
                intent=ImageEditIntent(prompt="test", images=(Path("in.png"),)),
                model_id="fake/create-only",
            )
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST

    def test_validate_rejects_unknown_model(self) -> None:
        with pytest.raises(PixgenError) as exc_info:
            _fake_registry().validate(intent=ImageCreateIntent(prompt="test"), model_id="fake/nope")
        assert exc_info.value.code == ErrorCode.MODEL_NOT_FOUND
