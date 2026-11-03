"""Tests for the OpenRouter image provider."""

import base64
import json
from pathlib import Path

import httpx2
import pytest
from pydantic import ValidationError

from pixgen.core.errors import ErrorCode, ProviderError
from pixgen.core.models import ImageOperation, MediaRole
from pixgen.core.parameters import ProviderParams
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent, ImageIntent
from pixgen.images.models import LocalImage
from pixgen.providers.base import PreparedImageRequest, PreparedMedia
from pixgen.providers.openrouter import (
    OPENROUTER_CATALOGUE,
    OpenRouterGeminiParams,
    OpenRouterGPTImageParams,
    OpenRouterProvider,
)
from pixgen.providers.registry import ProviderRegistry


class TestOpenRouterCatalogue:
    """Tests for OpenRouter model metadata and native parameters."""

    def test_catalogue_preserves_exact_upstream_model_slugs(self) -> None:
        assert [definition.spec.id for definition in OPENROUTER_CATALOGUE] == [
            "openrouter/google/gemini-3.1-flash-image",
            "openrouter/meta/muse-image",
            "openrouter/openai/gpt-image-2.5-sunburst",
        ]
        assert [definition.spec.model for definition in OPENROUTER_CATALOGUE] == [
            "google/gemini-3.1-flash-image",
            "meta/muse-image",
            "openai/gpt-image-2.5-sunburst",
        ]

    def test_catalogue_declares_edit_capability_and_reference_limits(self) -> None:
        gemini, muse, gpt = OPENROUTER_CATALOGUE

        assert gemini.spec.operations == {
            ImageOperation.IMAGE_CREATE,
            ImageOperation.IMAGE_EDIT,
        }
        assert gemini.spec.media[MediaRole.REFERENCE].maximum == 14
        assert muse.spec.operations == {ImageOperation.IMAGE_CREATE}
        assert MediaRole.REFERENCE not in muse.spec.media
        assert gpt.spec.operations == {ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT}
        assert gpt.spec.media[MediaRole.REFERENCE].maximum == 16

    def test_gemini_parameters_validate_resolution_and_aspect_ratio(self) -> None:
        params = OpenRouterGeminiParams(aspect_ratio="1:4", resolution="4K")

        assert params.aspect_ratio == "1:4"
        assert params.resolution == "4K"
        with pytest.raises(ValidationError):
            OpenRouterGeminiParams(aspect_ratio="5:7")
        with pytest.raises(ValidationError):
            OpenRouterGeminiParams(resolution="8K")

    def test_gpt_parameters_validate_quality_background_ratio_and_compression(self) -> None:
        params = OpenRouterGPTImageParams(
            aspect_ratio="auto",
            quality="xhigh",
            background="transparent",
            output_compression=72,
        )

        assert params.output_compression == 72
        assert params.aspect_ratio == "auto"
        with pytest.raises(ValidationError):
            OpenRouterGPTImageParams(quality="ultra")
        with pytest.raises(ValidationError):
            OpenRouterGPTImageParams(background="blur")
        with pytest.raises(ValidationError):
            OpenRouterGPTImageParams(aspect_ratio="1:4")
        with pytest.raises(ValidationError):
            OpenRouterGPTImageParams(output_compression=101)

    def test_catalogue_omits_batch_count_and_muse_native_parameters(self) -> None:
        assert "n" not in OpenRouterGPTImageParams.model_fields
        assert "n" not in OpenRouterGeminiParams.model_fields
        assert OPENROUTER_CATALOGUE[1].parameter_type is ProviderParams
        assert OPENROUTER_CATALOGUE[1].parameter_type.model_fields == {}

    def test_shared_aspect_ratios_match_model_capabilities(self) -> None:
        registry = ProviderRegistry((OpenRouterProvider(None),))

        assert registry.shared_aspect_ratios(
            "openrouter/google/gemini-3.1-flash-image", ImageOperation.IMAGE_CREATE
        ) == (
            "16:9",
            "1:1",
            "1:4",
            "1:8",
            "2:3",
            "3:2",
            "3:4",
            "4:1",
            "4:3",
            "4:5",
            "5:4",
            "7:3",
            "8:1",
            "9:16",
        )
        assert registry.shared_aspect_ratios(
            "openrouter/openai/gpt-image-2.5-sunburst", ImageOperation.IMAGE_CREATE
        ) == ("16:9", "1:1", "2:3", "3:2", "3:4", "4:3", "7:3", "9:16")
        assert (
            registry.shared_aspect_ratios("openrouter/meta/muse-image", ImageOperation.IMAGE_CREATE)
            == ()
        )


class TestOpenRouterProvider:
    """Tests for OpenRouter provider registration."""

    def test_has_name_and_catalogue(self) -> None:
        provider = OpenRouterProvider(None)

        assert provider.name == "openrouter"
        assert provider.catalogue == OPENROUTER_CATALOGUE


def _prepared_request(
    *,
    model_id: str,
    intent: ImageIntent,
    parameters: ProviderParams | None = None,
    media: tuple[PreparedMedia, ...] = (),
) -> PreparedImageRequest:
    registry = ProviderRegistry((OpenRouterProvider(None),))
    request = registry.validate(intent=intent, model_id=model_id, parameters=parameters)
    return PreparedImageRequest(request=request, media=media)


def _local_image(content: bytes, media_type: str, filename: str) -> LocalImage:
    return LocalImage(
        source_path=Path(f"/tmp/{filename}"),  # noqa: S108
        filename=filename,
        content=content,
        media_type=media_type,
    )


class TestOpenRouterGeneration:
    """Tests for OpenRouter request and response handling."""

    async def test_generate_posts_exact_slug_and_only_set_parameters(self) -> None:
        image_data = base64.b64encode(b"generated").decode()
        payloads: list[dict[str, object]] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            assert request.url.path == "/api/v1/images"
            payloads.append(json.loads(request.read()))
            return httpx2.Response(
                200,
                json={"data": [{"b64_json": image_data, "media_type": "image/webp"}]},
            )

        client = httpx2.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            transport=httpx2.MockTransport(handler),
        )
        provider = OpenRouterProvider(client)
        request = _prepared_request(
            model_id="openrouter/openai/gpt-image-2.5-sunburst",
            intent=ImageCreateIntent(prompt="A small red boat"),
            parameters=OpenRouterGPTImageParams(quality="high"),
        )

        result = await provider.generate(request)

        assert payloads == [
            {
                "model": "openai/gpt-image-2.5-sunburst",
                "prompt": "A small red boat",
                "quality": "high",
            }
        ]
        assert result.data == b"generated"
        assert result.media_type == "image/webp"
        await client.aclose()

    async def test_generate_includes_references_as_ordered_data_urls(self) -> None:
        image_data = base64.b64encode(b"result").decode()
        payloads: list[dict[str, object]] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            payloads.append(json.loads(request.read()))
            return httpx2.Response(200, json={"data": [{"b64_json": image_data}]})

        client = httpx2.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            transport=httpx2.MockTransport(handler),
        )
        provider = OpenRouterProvider(client)
        model_id = "openrouter/google/gemini-3.1-flash-image"
        references = (
            PreparedMedia(
                role=MediaRole.REFERENCE,
                image=_local_image(b"first image", "image/png", "first.png"),
            ),
            PreparedMedia(
                role=MediaRole.REFERENCE,
                image=_local_image(b"second image", "image/jpeg", "second.jpg"),
            ),
        )
        request = _prepared_request(
            model_id=model_id,
            intent=ImageEditIntent(prompt="Combine these references", images=(Path("one.png"),)),
            media=references,
        )

        await provider.generate(request)

        assert payloads[0]["input_references"] == [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,Zmlyc3QgaW1hZ2U="},
            },
            {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,c2Vjb25kIGltYWdl"},
            },
        ]
        await client.aclose()

    async def test_generate_defaults_missing_media_type_to_png(self) -> None:
        image_data = base64.b64encode(b"generated").decode()
        client = httpx2.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            transport=httpx2.MockTransport(
                lambda _request: httpx2.Response(200, json={"data": [{"b64_json": image_data}]})
            ),
        )
        provider = OpenRouterProvider(client)
        request = _prepared_request(
            model_id="openrouter/meta/muse-image",
            intent=ImageCreateIntent(prompt="A lighthouse"),
        )

        result = await provider.generate(request)

        assert result.media_type == "image/png"
        await client.aclose()

    async def test_generate_without_credentials_raises_safe_error(self) -> None:
        provider = OpenRouterProvider(None)
        request = _prepared_request(
            model_id="openrouter/meta/muse-image",
            intent=ImageCreateIntent(prompt="A lighthouse"),
        )

        with pytest.raises(ProviderError) as exc_info:
            await provider.generate(request)

        assert exc_info.value.code == ErrorCode.CREDENTIAL_UNAVAILABLE

    @pytest.mark.parametrize("encoded", ["private-not-base64", ""], ids=["invalid", "empty"])
    async def test_generate_rejects_invalid_response_safely(self, encoded: str) -> None:
        client = httpx2.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            transport=httpx2.MockTransport(
                lambda _request: httpx2.Response(200, json={"data": [{"b64_json": encoded}]})
            ),
        )
        provider = OpenRouterProvider(client)
        request = _prepared_request(
            model_id="openrouter/meta/muse-image",
            intent=ImageCreateIntent(prompt="A lighthouse"),
        )

        with pytest.raises(ProviderError) as exc_info:
            await provider.generate(request)

        assert exc_info.value.code == ErrorCode.PROVIDER_FAILURE
        assert "private-not-base64" not in str(exc_info.value)
        await client.aclose()


class TestOpenRouterErrorMapping:
    """Tests for safe OpenRouter error classification."""

    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            (401, "private provider text", ErrorCode.AUTHENTICATION_FAILED),
            (403, "private provider text", ErrorCode.AUTHENTICATION_FAILED),
            (404, "private provider text", ErrorCode.MODEL_NOT_FOUND),
            (429, "private provider text", ErrorCode.RATE_LIMITED),
            (422, "private provider text", ErrorCode.INVALID_REQUEST),
            (400, "content_policy blocked private prompt", ErrorCode.CONTENT_REJECTED),
            (500, "private provider text", ErrorCode.PROVIDER_UNAVAILABLE),
        ],
        ids=[
            "unauthorized",
            "forbidden",
            "missing-model",
            "rate-limit",
            "invalid",
            "policy",
            "server",
        ],
    )
    async def test_generate_maps_http_errors_without_exposing_body(
        self, status: int, body: str, expected: ErrorCode
    ) -> None:
        client = httpx2.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            transport=httpx2.MockTransport(lambda _request: httpx2.Response(status, text=body)),
        )
        provider = OpenRouterProvider(client)
        request = _prepared_request(
            model_id="openrouter/meta/muse-image",
            intent=ImageCreateIntent(prompt="A lighthouse"),
        )

        with pytest.raises(ProviderError) as exc_info:
            await provider.generate(request)

        assert exc_info.value.code == expected
        assert body not in str(exc_info.value)
        await client.aclose()

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (httpx2.ReadTimeout("private timeout"), ErrorCode.TIMEOUT),
            (
                httpx2.ConnectError(
                    "private connection detail",
                    request=httpx2.Request("POST", "https://openrouter.ai/api/v1/images"),
                ),
                ErrorCode.PROVIDER_UNAVAILABLE,
            ),
        ],
        ids=["timeout", "connection"],
    )
    async def test_generate_maps_transport_errors_safely(
        self, error: Exception, expected: ErrorCode
    ) -> None:
        client = httpx2.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            transport=httpx2.MockTransport(lambda _request: (_ for _ in ()).throw(error)),
        )
        provider = OpenRouterProvider(client)
        request = _prepared_request(
            model_id="openrouter/meta/muse-image",
            intent=ImageCreateIntent(prompt="A lighthouse"),
        )

        with pytest.raises(ProviderError) as exc_info:
            await provider.generate(request)

        assert exc_info.value.code == expected
        assert "private" not in str(exc_info.value)
        await client.aclose()
