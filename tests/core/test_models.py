"""Tests for core.models."""

import pytest
from pydantic import ValidationError

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.models import (
    ImageOperation,
    MediaRole,
    MediaRoleSpec,
    ModelId,
    ModelSpec,
    normalise_model_id,
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
            "openrouter/google/gemini-3.1-flash-image",
        ],
        ids=["openai", "gemini", "minimal", "hyphenated", "nested"],
    )
    def test_accepts_valid_model_ids(self, valid_id: str) -> None:

        from pydantic import TypeAdapter

        adapter = TypeAdapter(ModelId)
        result = adapter.validate_python(valid_id)
        assert result == valid_id

    def test_accepts_nested_provider_model_id(self) -> None:
        from pydantic import TypeAdapter

        result = TypeAdapter(ModelId).validate_python("openrouter/google/gemini-3.1-flash-image")

        assert result == "openrouter/google/gemini-3.1-flash-image"

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
            "openrouter//gemini-image",
            "openrouter/google/",
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
            "empty-intermediate-model-segment",
            "empty-trailing-model-segment",
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

    def test_model_spec_splits_nested_provider_model_id(self, model_spec: ModelSpec) -> None:
        spec = model_spec.model_copy(update={"id": "openrouter/google/gemini-3.1-flash-image"})

        assert spec.provider == "openrouter"
        assert spec.model == "google/gemini-3.1-flash-image"

    def test_frozen_raises_on_assignment(self, model_spec: ModelSpec) -> None:
        with pytest.raises(ValidationError):
            model_spec.display_name = "changed"


class TestNormaliseModelId:
    """Tests for normalise_model_id."""

    @pytest.mark.parametrize(
        ("value", "allow_nested", "expected"),
        [
            ("gpt-image-2", False, "openai/gpt-image-2"),
            ("openai/gpt-image-2", False, "openai/gpt-image-2"),
            ("google/gemini-3.1-flash-image", True, "openai/google/gemini-3.1-flash-image"),
            ("openai/google/gemini-3.1-flash-image", True, "openai/google/gemini-3.1-flash-image"),
        ],
        ids=["local", "prefixed", "nested", "nested-prefixed"],
    )
    def test_prefixes_provider_local_names(
        self, value: str, *, allow_nested: bool, expected: str
    ) -> None:
        assert (
            normalise_model_id(
                value, prefix="openai", error_message="bad model", allow_nested=allow_nested
            )
            == expected
        )

    @pytest.mark.parametrize(
        ("value", "allow_nested"),
        [("google/gemini-3.1-flash-image", False), ("Not A Model", True)],
        ids=["nested-not-allowed", "invalid-nested"],
    )
    def test_rejects_invalid_names(self, value: str, *, allow_nested: bool) -> None:
        with pytest.raises(PixgenError) as exc_info:
            normalise_model_id(
                value, prefix="openai", error_message="bad model", allow_nested=allow_nested
            )

        assert exc_info.value.code is ErrorCode.INVALID_REQUEST
        assert exc_info.value.message == "bad model"
