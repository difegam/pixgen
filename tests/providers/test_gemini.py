"""Tests for providers.gemini."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pixgen.core.errors import PixgenError
from pixgen.core.models import ImageOperation, MediaRole
from pixgen.core.requests import ImageCreateIntent
from pixgen.images.models import LocalImage
from pixgen.providers.base import PreparedImageRequest, PreparedMedia
from pixgen.providers.gemini import GEMINI_MODELS, GeminiParams, GeminiProvider


def _make_local_image(
    content: bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
    media_type: str = "image/png",
) -> LocalImage:
    from pathlib import Path

    return LocalImage(
        source_path=Path("/tmp/test.png"),  # noqa: S108
        filename="test.png",
        content=content,
        media_type=media_type,
    )


class TestGeminiParams:
    """Tests for Gemini parameter validation."""

    def test_valid_params(self) -> None:
        params = GeminiParams(aspect_ratio="16:9", image_size="2K")
        assert params.aspect_ratio == "16:9"
        assert params.image_size == "2K"

    def test_invalid_aspect_ratio_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            GeminiParams(aspect_ratio="invalid")

    def test_invalid_image_size_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            GeminiParams(image_size="8K")

    def test_lite_model_rejects_sizes_above_1k(self) -> None:
        provider = GeminiProvider(None)
        intent = ImageCreateIntent(prompt="test")

        with pytest.raises(PixgenError, match="invalid parameters"):
            provider.validate(
                intent=intent, model=GEMINI_MODELS[1], parameters=GeminiParams(image_size="2K")
            )


class TestGeminiProvider:
    """Tests for GeminiProvider."""

    def test_models_returns_catalog(self) -> None:
        provider = GeminiProvider(None)
        assert provider.models() == GEMINI_MODELS
        assert len(provider.models()) == 3

    def test_available_false_without_client(self) -> None:
        provider = GeminiProvider(None)
        assert provider.available is False

    def test_validate_returns_validated_request(self) -> None:
        provider = GeminiProvider(None)
        intent = ImageCreateIntent(prompt="test")
        model = GEMINI_MODELS[0]
        result = provider.validate(
            intent=intent, model=model, parameters=GeminiParams(aspect_ratio="1:1")
        )
        assert result.parameters == GeminiParams(aspect_ratio="1:1")

    def test_declared_media_type_always_none(self) -> None:
        provider = GeminiProvider(None)
        intent = ImageCreateIntent(prompt="test")
        model = GEMINI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        assert provider.declared_media_type(request) is None

    def test_parameter_schema_returns_json_schema(self) -> None:
        provider = GeminiProvider(None)
        schema = provider.parameter_schema(
            "gemini/gemini-3.1-flash-image", ImageOperation.IMAGE_CREATE
        )
        assert "properties" in schema
        assert "aspect_ratio" in schema["properties"]

    def test_lite_parameter_schema_only_allows_1k(self) -> None:
        provider = GeminiProvider(None)
        schema = provider.parameter_schema(
            "gemini/gemini-3.1-flash-lite-image", ImageOperation.IMAGE_CREATE
        )

        image_size_schema = schema["properties"]["image_size"]
        assert image_size_schema["anyOf"][0]["const"] == "1K"
        assert image_size_schema["anyOf"][1] == {"type": "null"}

    @pytest.mark.asyncio
    async def test_generate_without_client_raises(self) -> None:
        provider = GeminiProvider(None)
        intent = ImageCreateIntent(prompt="test")
        model = GEMINI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        prepared = PreparedImageRequest(request=request, media=())
        with pytest.raises(Exception, match="credential"):
            await provider.generate(prepared)

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_part = MagicMock()
        mock_part.inline_data = MagicMock()
        mock_part.inline_data.data = b"gemini image data"
        mock_part.inline_data.mime_type = "image/png"
        mock_response.parts = [mock_part]

        mock_chat = AsyncMock()
        mock_chat.send_message = AsyncMock(return_value=mock_response)
        mock_client.aio.chats.create = MagicMock(return_value=mock_chat)

        provider = GeminiProvider(mock_client)
        intent = ImageCreateIntent(prompt="test prompt")
        model = GEMINI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        prepared = PreparedImageRequest(request=request, media=())

        result = await provider.generate(prepared)
        assert result.data == b"gemini image data"
        assert result.media_type == "image/png"

    @pytest.mark.asyncio
    async def test_generate_with_media(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_part = MagicMock()
        mock_part.inline_data = MagicMock()
        mock_part.inline_data.data = b"edited"
        mock_part.inline_data.mime_type = "image/jpeg"
        mock_response.parts = [mock_part]

        mock_chat = AsyncMock()
        mock_chat.send_message = AsyncMock(return_value=mock_response)
        mock_client.aio.chats.create = MagicMock(return_value=mock_chat)

        provider = GeminiProvider(mock_client)
        intent = ImageCreateIntent(prompt="test")
        model = GEMINI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        local_image = _make_local_image()
        media = (PreparedMedia(role=MediaRole.REFERENCE, image=local_image),)
        prepared = PreparedImageRequest(request=request, media=media)

        result = await provider.generate(prepared)
        assert result.data == b"edited"

    @pytest.mark.asyncio
    async def test_generate_no_image_in_response_raises(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parts = []
        mock_response.candidates = []

        mock_chat = AsyncMock()
        mock_chat.send_message = AsyncMock(return_value=mock_response)
        mock_client.aio.chats.create = MagicMock(return_value=mock_chat)

        provider = GeminiProvider(mock_client)
        intent = ImageCreateIntent(prompt="test")
        model = GEMINI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        prepared = PreparedImageRequest(request=request, media=())

        with pytest.raises(Exception, match="no image"):
            await provider.generate(prepared)
