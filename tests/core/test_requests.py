"""Tests for core.requests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pixgen.core.models import ImageOperation
from pixgen.core.requests import (
    ImageCreateIntent,
    ImageEditIntent,
    ImageIntent,
    ValidatedImageRequest,
)


class TestImageCreateIntent:
    """Tests for ImageCreateIntent."""

    def test_valid_create_intent(self) -> None:
        intent = ImageCreateIntent(prompt="A sunset", references=(Path("ref.png"),))
        assert intent.operation == ImageOperation.IMAGE_CREATE
        assert intent.prompt == "A sunset"
        assert len(intent.references) == 1

    def test_empty_references_allowed(self) -> None:
        intent = ImageCreateIntent(prompt="A sunset")
        assert intent.references == ()

    def test_empty_prompt_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImageCreateIntent(prompt="")

    def test_whitespace_prompt_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-whitespace"):
            ImageCreateIntent(prompt="   ")

    def test_frozen_raises_on_assignment(self) -> None:
        intent = ImageCreateIntent(prompt="test")
        with pytest.raises(ValidationError):
            intent.prompt = "changed"


class TestImageEditIntent:
    """Tests for ImageEditIntent."""

    def test_valid_edit_intent(self) -> None:
        intent = ImageEditIntent(prompt="Make it blue", images=(Path("source.png"),))
        assert intent.operation == ImageOperation.IMAGE_EDIT
        assert len(intent.images) == 1

    def test_multiple_images_allowed(self) -> None:
        intent = ImageEditIntent(
            prompt="Combine",
            images=(Path("a.png"), Path("b.png"), Path("c.png")),
        )
        assert len(intent.images) == 3

    def test_empty_images_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImageEditIntent(prompt="test", images=())

    def test_empty_prompt_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImageEditIntent(prompt="", images=(Path("x.png"),))


class TestImageIntentDiscrimination:
    """Tests for ImageIntent discriminated union."""

    def test_discriminates_create(self) -> None:

        from pydantic import TypeAdapter

        adapter = TypeAdapter(ImageIntent)
        data = {"operation": "image-create", "prompt": "test"}
        result = adapter.validate_python(data)
        assert isinstance(result, ImageCreateIntent)

    def test_discriminates_edit(self) -> None:

        from pydantic import TypeAdapter

        adapter = TypeAdapter(ImageIntent)
        data = {
            "operation": "image-edit",
            "prompt": "test",
            "images": ["source.png"],
        }
        result = adapter.validate_python(data)
        assert isinstance(result, ImageEditIntent)


class TestValidatedImageRequest:
    """Tests for ValidatedImageRequest."""

    def test_valid_request(self, model_spec) -> None:
        intent = ImageCreateIntent(prompt="test")
        request = ValidatedImageRequest(
            intent=intent,
            model=model_spec,
            parameters={"quality": "high"},
        )
        assert request.intent.prompt == "test"
        assert request.model.id == "openai/gpt-image-2"
        assert request.parameters == {"quality": "high"}

    def test_frozen_raises_on_assignment(self, model_spec) -> None:
        intent = ImageCreateIntent(prompt="test")
        request = ValidatedImageRequest(intent=intent, model=model_spec, parameters={})
        with pytest.raises(ValidationError):
            request.parameters = {"x": 1}
