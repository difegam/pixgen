"""Tests for model definitions."""

from typing import Literal

import pytest
from pydantic import ValidationError

from pixgen.core.definitions import ModelDefinition
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.parameters import ProviderParams, SharedImageParams
from tests.factories import make_model_spec


class DemoParams(ProviderParams):
    """Native parameters used by definition tests."""

    size: Literal["small", "large"] = "small"


class LooseParams(ProviderParams):
    """Broader native parameters, as a provider CLI builds them."""

    size: str = "small"


def make_definition(**ratios: dict[str, object]) -> ModelDefinition[DemoParams]:
    return ModelDefinition[DemoParams](
        spec=make_model_spec(),
        parameter_type=DemoParams,
        defaults=DemoParams(),
        aspect_ratios=ratios,
    )


class TestModelDefinition:
    """Test native parameter resolution."""

    def test_omitted_ratio_preserves_defaults(self) -> None:
        definition = make_definition(**{"1:1": {"size": "large"}})
        assert definition.resolve(SharedImageParams()).size == "small"

    def test_ratio_applies_native_override(self) -> None:
        definition = make_definition(**{"1:1": {"size": "large"}})
        assert definition.resolve(SharedImageParams(aspect_ratio="2:2")).size == "large"

    def test_unsupported_ratio_is_rejected(self) -> None:
        definition = make_definition(**{"1:1": {"size": "large"}})
        with pytest.raises(ValueError, match="unsupported aspect ratio"):
            definition.resolve(SharedImageParams(aspect_ratio="3:2"))

    def test_empty_ratio_override_preserves_native_defaults(self) -> None:
        definition = make_definition(**{"1:1": {}})

        assert definition.resolve(SharedImageParams(aspect_ratio="1:1")).size == "small"

    def test_invalid_override_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValidationError):
            make_definition(**{"1:1": {"size": "invalid"}})

    def test_canonical_key_collision_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="canonical aspect ratio"):
            make_definition(**{"16:9": {"size": "small"}, "32:18": {"size": "large"}})

    def test_definition_copies_input_mappings(self) -> None:
        ratios = {"1:1": {"size": "large"}}
        definition = make_definition(**ratios)
        ratios["1:1"]["size"] = "small"
        assert definition.resolve(SharedImageParams(aspect_ratio="1:1")).size == "large"

    def test_resolve_parameters_defaults_when_omitted(self) -> None:
        definition = make_definition(**{"1:1": {"size": "large"}})
        assert definition.resolve_parameters(None) == DemoParams()

    def test_resolve_parameters_maps_shared_ratio(self) -> None:
        definition = make_definition(**{"1:1": {"size": "large"}})
        resolved = definition.resolve_parameters(SharedImageParams(aspect_ratio="1:1"))
        assert resolved == DemoParams(size="large")

    def test_resolve_parameters_rejects_unsupported_ratio_listing_supported(self) -> None:
        definition = make_definition(**{"1:1": {"size": "large"}})
        with pytest.raises(PixgenError, match="supported ratios: 1:1") as exc_info:
            definition.resolve_parameters(SharedImageParams(aspect_ratio="3:2"))
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST

    def test_resolve_parameters_revalidates_native_parameters(self) -> None:
        definition = make_definition()
        resolved = definition.resolve_parameters(LooseParams(size="large"))
        assert type(resolved) is DemoParams
        assert resolved.size == "large"

    def test_resolve_parameters_rejects_native_values_outside_model_type(self) -> None:
        definition = make_definition()
        with pytest.raises(PixgenError, match="invalid parameters") as exc_info:
            definition.resolve_parameters(LooseParams(size="huge"))
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST

    def test_parameter_type_is_not_serialised(self) -> None:
        dumped = make_definition().model_dump()
        assert "parameter_type" not in dumped
