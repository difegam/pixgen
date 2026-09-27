"""Tests for composed provider and model definitions."""

from typing import Literal

import pytest
from pydantic import ValidationError

from pixgen.core.definitions import ModelDefinition, OperationDefinition, ProviderDefinition
from pixgen.core.models import ImageOperation
from pixgen.core.parameters import ProviderParams, SharedImageParams
from tests.factories import make_model_spec


class DemoParams(ProviderParams):
    """Native parameters used by definition tests."""

    size: Literal["small", "large"] = "small"


def make_operation(**ratios: dict[str, object]) -> OperationDefinition[DemoParams]:
    return OperationDefinition[DemoParams](
        parameter_type=DemoParams,
        defaults=DemoParams(),
        media={},
        aspect_ratios=ratios,
    )


class TestOperationDefinition:
    """Test native parameter resolution."""

    def test_omitted_ratio_preserves_defaults(self) -> None:
        definition = make_operation(**{"1:1": {"size": "large"}})
        assert definition.resolve(SharedImageParams()).size == "small"

    def test_ratio_applies_native_override(self) -> None:
        definition = make_operation(**{"1:1": {"size": "large"}})
        assert definition.resolve(SharedImageParams(aspect_ratio="2:2")).size == "large"

    def test_unsupported_ratio_is_rejected(self) -> None:
        definition = make_operation(**{"1:1": {"size": "large"}})
        with pytest.raises(ValueError, match="unsupported aspect ratio"):
            definition.resolve(SharedImageParams(aspect_ratio="3:2"))

    def test_empty_ratio_override_preserves_native_defaults(self) -> None:
        definition = make_operation(**{"1:1": {}})

        assert definition.resolve(SharedImageParams(aspect_ratio="1:1")).size == "small"

    def test_invalid_override_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValidationError):
            make_operation(**{"1:1": {"size": "invalid"}})

    def test_canonical_key_collision_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="canonical aspect ratio"):
            make_operation(**{"16:9": {"size": "small"}, "32:18": {"size": "large"}})

    def test_definition_copies_input_mappings(self) -> None:
        ratios = {"1:1": {"size": "large"}}
        definition = make_operation(**ratios)
        ratios["1:1"]["size"] = "small"
        assert definition.resolve(SharedImageParams(aspect_ratio="1:1")).size == "large"


class TestProviderDefinition:
    """Test provider catalogue composition."""

    def test_rejects_duplicate_model_ids(self) -> None:
        spec = make_model_spec(operations=frozenset({ImageOperation.IMAGE_CREATE}))
        model = ModelDefinition[DemoParams](
            spec=spec,
            operations={ImageOperation.IMAGE_CREATE: make_operation()},
        )
        with pytest.raises(ValidationError, match="duplicate model"):
            ProviderDefinition[ModelDefinition[DemoParams]](
                name="openai",
                models=(model, model),
            )

    def test_rejects_model_owned_by_another_provider(self) -> None:
        spec = make_model_spec(
            model_id="gemini/demo",
            operations=frozenset({ImageOperation.IMAGE_CREATE}),
        )
        model = ModelDefinition[DemoParams](
            spec=spec,
            operations={ImageOperation.IMAGE_CREATE: make_operation()},
        )
        with pytest.raises(ValidationError, match="provider prefix"):
            ProviderDefinition[ModelDefinition[DemoParams]](name="openai", models=(model,))
