"""Tests for core.models."""

import pytest
from pydantic import ValidationError

from pixgen.core.models import (
    ImageOperation,
    MediaRole,
    MediaRoleSpec,
    ModelId,
    ModelSpec,
)


class TestModelId:
    """Tests for ModelId pattern validation."""

    @pytest.mark.parametrize(
        "valid_id",
        [
            "openai/gpt-image-2",
            "gemini/gemini-3.1-flash-image",
            "a/b",
            "openai-2/gpt-image-1.5",
        ],
        ids=["openai", "gemini", "minimal", "hyphenated"],
    )
    def test_accepts_valid_model_ids(self, valid_id: str) -> None:

        from pydantic import TypeAdapter

        adapter = TypeAdapter(ModelId)
        result = adapter.validate_python(valid_id)
        assert result == valid_id

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "",
            "no-slash",
            "/starts-with-slash",
            "ends-with-slash/",
            "UPPER/model",
            "openai/",
            "openai/Model",
            "openai/ model",
            "/m",
            "m/",
        ],
        ids=[
            "empty",
            "no-slash",
            "leading-slash",
            "trailing-slash",
            "uppercase-provider",
            "empty-model",
            "uppercase-model",
            "space-in-model",
            "minimal-length",
            "minimal-length",
        ],
    )
    def test_rejects_invalid_model_ids(self, invalid_id: str) -> None:

        from pydantic import TypeAdapter

        adapter = TypeAdapter(ModelId)
        with pytest.raises(ValidationError):
            adapter.validate_python(invalid_id)


class TestMediaRoleSpec:
    """Tests for MediaRoleSpec validation."""

    def test_valid_spec(self) -> None:
        spec = MediaRoleSpec(
            minimum=0,
            maximum=16,
            formats=frozenset({"png", "jpeg"}),
            max_bytes=50_000_000,
        )
        assert spec.minimum == 0
        assert spec.maximum == 16
        assert spec.max_bytes == 50_000_000

    def test_minimum_exceeds_maximum_raises(self) -> None:
        with pytest.raises(ValidationError, match="minimum cannot exceed maximum"):
            MediaRoleSpec(minimum=10, maximum=5, formats=frozenset({"png"}))

    def test_frozen_raises_on_assignment(self) -> None:
        spec = MediaRoleSpec(minimum=0, maximum=1, formats=frozenset({"png"}))
        with pytest.raises(ValidationError):
            spec.minimum = 5

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            MediaRoleSpec(minimum=0, maximum=1, formats=frozenset({"png"}), unknown_field="x")


class TestImageOperation:
    """Tests for ImageOperation enum."""

    def test_values(self) -> None:
        assert ImageOperation.IMAGE_CREATE == "image-create"
        assert ImageOperation.IMAGE_EDIT == "image-edit"


class TestMediaRole:
    """Tests for MediaRole enum."""

    def test_values(self) -> None:
        assert MediaRole.REFERENCE == "reference"
        assert MediaRole.IMAGE == "image"


class TestModelSpec:
    """Tests for ModelSpec."""

    def test_valid_spec(self, model_spec: ModelSpec) -> None:
        assert model_spec.id == "openai/gpt-image-2"
        assert MediaRole.REFERENCE in model_spec.media
        assert MediaRole.IMAGE in model_spec.media

    def test_frozen_raises_on_assignment(self, model_spec: ModelSpec) -> None:
        with pytest.raises(ValidationError):
            model_spec.display_name = "changed"
