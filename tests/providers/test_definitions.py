"""Tests for provider catalogues."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pixgen.core.definitions import ModelDefinition
from pixgen.core.errors import PixgenError
from pixgen.core.models import ImageOperation
from pixgen.core.parameters import SharedImageParams
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent
from pixgen.providers.gemini import GEMINI_CATALOGUE, GeminiParams, GeminiProvider
from pixgen.providers.openai import (
    OPENAI_CATALOGUE,
    OpenAIMiniParams,
    OpenAIParams,
    OpenAIProvider,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pixgen.core.requests import ImageIntent


def _definition[D: ModelDefinition](catalogue: Iterable[D], model_id: str) -> D:
    return next(item for item in catalogue if item.spec.id == model_id)


_INTENTS = [
    pytest.param(ImageCreateIntent(prompt="test"), id="create"),
    pytest.param(ImageEditIntent(prompt="test", images=(Path("in.png"),)), id="edit"),
]


_CATALOGUE_CASES = [
    pytest.param(OpenAIProvider(None), definition, id=definition.spec.id)
    for definition in OPENAI_CATALOGUE
] + [
    pytest.param(GeminiProvider(None), definition, id=definition.spec.id)
    for definition in GEMINI_CATALOGUE
]


class TestCatalogueAgreement:
    """Published schemas and validation read the same model definition."""

    @pytest.mark.parametrize(("provider", "definition"), _CATALOGUE_CASES)
    def test_models_project_catalogue_specs(self, provider, definition) -> None:
        assert definition.spec in provider.models()

    @pytest.mark.parametrize(("provider", "definition"), _CATALOGUE_CASES)
    def test_schema_matches_definition_parameter_type(self, provider, definition) -> None:
        for operation in definition.spec.operations:
            assert (
                provider.parameter_schema(definition.spec.id, operation)
                == definition.parameter_type.model_json_schema()
            )

    @pytest.mark.parametrize(
        ("provider", "model_id", "params"),
        [
            pytest.param(
                OpenAIProvider(None),
                "openai/gpt-image-1-mini",
                OpenAIParams(size="1792x768"),
                id="mini-rejects-wide-size",
            ),
            pytest.param(
                GeminiProvider(None),
                "gemini/gemini-3.1-flash-lite-image",
                GeminiParams(image_size="4K"),
                id="lite-rejects-4k",
            ),
            pytest.param(
                GeminiProvider(None),
                "gemini/gemini-3.1-flash-image",
                OpenAIParams(quality="high"),
                id="gemini-rejects-openai-params",
            ),
        ],
    )
    def test_validate_enforces_model_parameter_type(self, provider, model_id, params) -> None:
        spec = _definition(OPENAI_CATALOGUE + GEMINI_CATALOGUE, model_id).spec
        with pytest.raises(PixgenError, match="invalid parameters"):
            provider.validate(
                intent=ImageCreateIntent(prompt="test"), model=spec, parameters=params
            )


class TestOpenAICatalogue:
    """Test OpenAI ratio mappings."""

    def test_gpt_image_two_maps_wide_ratio(self) -> None:
        definition = _definition(OPENAI_CATALOGUE, "openai/gpt-image-2")
        assert definition.resolve(SharedImageParams(aspect_ratio="16:9")).size == "1536x864"

    def test_mini_rejects_unmapped_wide_ratio(self) -> None:
        definition = _definition(OPENAI_CATALOGUE, "openai/gpt-image-1-mini")
        with pytest.raises(ValueError, match="unsupported aspect ratio"):
            definition.resolve(SharedImageParams(aspect_ratio="16:9"))

    def test_omitted_ratio_keeps_size_default(self) -> None:
        definition = _definition(OPENAI_CATALOGUE, "openai/gpt-image-2")
        assert definition.resolve(SharedImageParams()).size is None

    @pytest.mark.parametrize("intent", _INTENTS)
    def test_validate_resolves_shared_ratio(self, intent: ImageIntent) -> None:
        request = OpenAIProvider(None).validate(
            intent=intent,
            model=_definition(OPENAI_CATALOGUE, "openai/gpt-image-2").spec,
            parameters=SharedImageParams(aspect_ratio="16:9"),
        )
        assert isinstance(request.parameters, OpenAIParams)
        assert request.parameters.size == "1536x864"

    def test_validate_rejects_unsupported_shared_ratio(self) -> None:
        with pytest.raises(PixgenError, match="supported ratios: 1:1, 2:3, 3:2"):
            OpenAIProvider(None).validate(
                intent=ImageCreateIntent(prompt="test"),
                model=_definition(OPENAI_CATALOGUE, "openai/gpt-image-1-mini").spec,
                parameters=SharedImageParams(aspect_ratio="16:9"),
            )

    def test_validate_without_parameters_uses_model_defaults(self) -> None:
        definition = _definition(OPENAI_CATALOGUE, "openai/gpt-image-1-mini")
        request = OpenAIProvider(None).validate(
            intent=ImageCreateIntent(prompt="test"), model=definition.spec
        )
        assert request.parameters == definition.defaults
        assert isinstance(request.parameters, OpenAIMiniParams)


class TestGeminiCatalogue:
    """Test Gemini ratio mappings."""

    def test_canonical_wide_ratio_uses_native_spelling(self) -> None:
        definition = _definition(GEMINI_CATALOGUE, "gemini/gemini-3.1-flash-image")
        params = definition.resolve(SharedImageParams(aspect_ratio="21:9"))
        assert params.aspect_ratio == "21:9"

    def test_lite_leaves_image_size_unset(self) -> None:
        definition = _definition(GEMINI_CATALOGUE, "gemini/gemini-3.1-flash-lite-image")
        assert definition.defaults.image_size is None

    @pytest.mark.parametrize("operation", list(ImageOperation))
    def test_lists_shared_ratios_through_provider_contract(self, operation: ImageOperation) -> None:
        assert "7:3" in GeminiProvider(None).shared_aspect_ratios(
            "gemini/gemini-3.1-flash-image",
            operation,
        )
