"""Tests for providers.openai."""

import base64
import json

import httpx2
import pytest

from pixgen.core.errors import ErrorCode
from pixgen.core.models import ImageOperation, MediaRole
from pixgen.core.requests import ImageCreateIntent
from pixgen.images.models import LocalImage
from pixgen.providers.base import PreparedImageRequest, PreparedMedia
from pixgen.providers.openai import OPENAI_MODELS, OpenAIParams, OpenAIProvider


def _make_local_image(
    content: bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
    media_type: str = "image/png",
    filename: str = "test.png",
) -> LocalImage:
    from pathlib import Path

    return LocalImage(
        source_path=Path(f"/tmp/{filename}"),  # noqa: S108
        filename=filename,
        content=content,
        media_type=media_type,
    )


class TestOpenAIParams:
    """Tests for OpenAI parameter validation."""

    def test_valid_params(self) -> None:
        params = OpenAIParams(
            size="1024x1024",
            quality="high",
            output_format="png",
        )
        assert params.size == "1024x1024"
        assert params.quality == "high"

    def test_invalid_quality_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            OpenAIParams(quality="invalid")

    def test_compression_out_of_range(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            OpenAIParams(output_compression=150)

    def test_compression_rejects_boolean(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            OpenAIParams(output_compression=True)

    def test_invalid_parameter_has_safe_provider_error(self) -> None:
        provider = OpenAIProvider(None)

        with pytest.raises(Exception) as exc_info:  # noqa: PT011
            provider.validate(
                intent=ImageCreateIntent(prompt="test", params={"quality": "bogus"}),
                model=OPENAI_MODELS[0],
            )

        assert exc_info.value.code == ErrorCode.INVALID_REQUEST
        assert "bogus" not in str(exc_info.value)


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_models_returns_catalog(self) -> None:
        provider = OpenAIProvider(None)
        assert provider.models() == OPENAI_MODELS
        assert len(provider.models()) == 2

    def test_available_false_without_client(self) -> None:
        provider = OpenAIProvider(None)
        assert provider.available is False

    def test_available_true_with_client(self) -> None:
        client = httpx2.AsyncClient()
        provider = OpenAIProvider(client)
        assert provider.available is True

    def test_validate_returns_validated_request(self) -> None:
        provider = OpenAIProvider(None)
        intent = ImageCreateIntent(
            prompt="test",
            params={"quality": "high"},
        )
        model = OPENAI_MODELS[0]
        result = provider.validate(intent=intent, model=model)
        assert result.intent is intent
        assert result.model is model
        assert result.parameters["quality"] == "high"

    def test_declared_media_type_with_output_format(self) -> None:
        provider = OpenAIProvider(None)
        intent = ImageCreateIntent(prompt="test")
        model = OPENAI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        request = request.model_copy(update={"parameters": {"output_format": "jpeg"}})
        assert provider.declared_media_type(request) == "image/jpeg"

    def test_declared_media_type_none_without_format(self) -> None:
        provider = OpenAIProvider(None)
        intent = ImageCreateIntent(prompt="test")
        model = OPENAI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        assert provider.declared_media_type(request) is None

    def test_parameter_schema_returns_json_schema(self) -> None:
        provider = OpenAIProvider(None)
        schema: dict = provider.parameter_schema("openai/gpt-image-2", ImageOperation.IMAGE_CREATE)
        assert "properties" in schema
        assert "quality" in schema["properties"]

    @pytest.mark.asyncio
    async def test_generate_without_client_raises(self) -> None:
        provider = OpenAIProvider(None)
        intent = ImageCreateIntent(prompt="test")
        model = OPENAI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        prepared = PreparedImageRequest(request=request, media=())
        with pytest.raises(Exception, match="credential"):
            await provider.generate(prepared)

    @pytest.mark.asyncio
    async def test_generate_json_success(self) -> None:
        b64_data = base64.b64encode(b"fake image data").decode()
        response_data = {
            "data": [{"b64_json": b64_data}],
            "output_format": "png",
        }

        def handler(request: httpx2.Request) -> httpx2.Response:
            assert "/images/generations" in str(request.url)
            return httpx2.Response(200, json=response_data)

        transport = httpx2.MockTransport(handler)
        client = httpx2.AsyncClient(transport=transport)
        provider = OpenAIProvider(client)

        intent = ImageCreateIntent(prompt="test prompt")
        model = OPENAI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        prepared = PreparedImageRequest(request=request, media=())

        result = await provider.generate(prepared)
        assert result.data == b"fake image data"
        assert result.media_type == "image/png"

    @pytest.mark.asyncio
    async def test_generate_json_uses_selected_model(self) -> None:
        b64_data = base64.b64encode(b"fake image data").decode()
        selected_model = OPENAI_MODELS[1]
        observed_models: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            observed_models.append(request.read().decode())
            return httpx2.Response(200, json={"data": [{"b64_json": b64_data}]})

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        provider = OpenAIProvider(client)
        intent = ImageCreateIntent(prompt="test prompt")
        request = provider.validate(intent=intent, model=selected_model)

        await provider.generate(PreparedImageRequest(request=request, media=()))

        assert json.loads(observed_models[0])["model"] == "gpt-image-1-mini"

    @pytest.mark.asyncio
    async def test_invalid_image_response_is_safe_provider_error(self) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, json={"data": [{"b64_json": "not-base64"}]})

        provider = OpenAIProvider(httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
        request = provider.validate(intent=ImageCreateIntent(prompt="test"), model=OPENAI_MODELS[0])

        with pytest.raises(Exception) as exc_info:  # noqa: PT011
            await provider.generate(PreparedImageRequest(request=request, media=()))

        assert exc_info.value.code == ErrorCode.PROVIDER_FAILURE
        assert "not-base64" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_multipart_with_references(self) -> None:
        b64_data = base64.b64encode(b"edited image").decode()
        response_data = {
            "data": [{"b64_json": b64_data}],
            "output_format": "jpeg",
        }

        def handler(request: httpx2.Request) -> httpx2.Response:
            assert "/images/edits" in str(request.url)
            return httpx2.Response(200, json=response_data)

        transport = httpx2.MockTransport(handler)
        client = httpx2.AsyncClient(transport=transport)
        provider = OpenAIProvider(client)

        intent = ImageCreateIntent(prompt="test", references=("/tmp/ref.png",))  # noqa: S108
        model = OPENAI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        local_image = _make_local_image()
        media = (PreparedMedia(role=MediaRole.REFERENCE, image=local_image),)
        prepared = PreparedImageRequest(request=request, media=media)

        result = await provider.generate(prepared)
        assert result.data == b"edited image"
        assert result.media_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_error_mapping_401(self) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(401, json={"error": {"message": "invalid key"}})

        transport = httpx2.MockTransport(handler)
        client = httpx2.AsyncClient(transport=transport)
        provider = OpenAIProvider(client)

        intent = ImageCreateIntent(prompt="test")
        model = OPENAI_MODELS[0]
        request = provider.validate(intent=intent, model=model)
        prepared = PreparedImageRequest(request=request, media=())

        with pytest.raises(Exception) as exc_info:  # noqa: PT011
            await provider.generate(prepared)
        assert exc_info.value.code == ErrorCode.AUTHENTICATION_FAILED
