"""OpenAI image generation adapter."""

import base64
import binascii
import json
from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from pixgen.core.definitions import ModelDefinition
from pixgen.core.errors import ErrorCode, PixgenError, ProviderError
from pixgen.core.models import (
    ImageOperation,
    JsonObject,
    MediaRole,
    MediaRoleSpec,
    ModelSpec,
)
from pixgen.core.parameters import ProviderParams
from pixgen.core.requests import (
    ImageCreateIntent,
    ImageEditIntent,
    ValidatedImageRequest,
)
from pixgen.providers.base import (
    PreparedImageRequest,
    ProviderImage,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx2

__all__: list[str] = [
    "OPENAI_CATALOGUE",
    "OPENAI_MODELS",
    "OpenAIParams",
    "OpenAIProvider",
]

_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIParams(ProviderParams):
    """Validated parameters for OpenAI image models."""

    size: str | None = Field(default=None, description="Image size preset or WxH")
    quality: Literal["low", "medium", "high", "auto"] | None = Field(
        default=None, description="Generation quality"
    )
    background: Literal["transparent", "opaque", "auto"] | None = Field(
        default=None, description="Background type"
    )
    output_format: Literal["png", "jpeg", "webp"] | None = Field(
        default=None, description="Output format"
    )
    output_compression: StrictInt | None = Field(
        default=None, ge=0, le=100, description="Compression level for jpeg/webp"
    )
    moderation: Literal["auto", "low"] | None = Field(
        default=None, description="Content moderation level"
    )


class OpenAIMiniParams(OpenAIParams):
    """Parameters supported by the GPT Image 1 Mini model."""

    size: Literal["1024x1024", "1024x1536", "1536x1024"] | None = Field(
        default=None,
        description="Image size preset",
    )


class _OpenAIImageItem(BaseModel):
    """Minimum image item returned by the OpenAI image endpoints."""

    model_config = ConfigDict(extra="allow")

    b64_json: str = Field(min_length=1)


class _OpenAIImageResponse(BaseModel):
    """Minimum response envelope returned by the OpenAI image endpoints."""

    model_config = ConfigDict(extra="allow")

    data: tuple[_OpenAIImageItem, ...] = Field(min_length=1)
    output_format: Literal["png", "jpeg", "webp"] = "png"


_OPENAI_RATIO_SIZES: dict[str, str] = {
    "1:1": "1024x1024",
    "2:3": "1024x1536",
    "3:2": "1536x1024",
    "3:4": "864x1152",
    "4:3": "1152x864",
    "9:16": "864x1536",
    "16:9": "1536x864",
    "7:3": "1792x768",
}


def _openai_definition(
    model_id: str,
    display_name: str,
    *,
    parameter_type: type[OpenAIParams],
    ratios: tuple[str, ...] = tuple(_OPENAI_RATIO_SIZES),
) -> ModelDefinition[OpenAIParams]:
    """Define one OpenAI model."""
    reference_spec = MediaRoleSpec(
        minimum=0,
        maximum=16,
        formats=frozenset({"png", "jpeg", "webp"}),
        max_bytes=52_428_800,
    )
    image_spec = MediaRoleSpec(
        minimum=1,
        maximum=16,
        formats=frozenset({"png", "jpeg", "webp"}),
        max_bytes=52_428_800,
    )
    spec = ModelSpec(
        id=model_id,
        display_name=display_name,
        operations=frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT}),
        media={MediaRole.REFERENCE: reference_spec, MediaRole.IMAGE: image_spec},
        documentation_url="https://platform.openai.com/docs/guides/images",
        verified_at=date(2026, 9, 24),
    )
    return ModelDefinition[OpenAIParams](
        spec=spec,
        parameter_type=parameter_type,
        defaults=parameter_type(),
        aspect_ratios={ratio: {"size": _OPENAI_RATIO_SIZES[ratio]} for ratio in ratios},
    )


OPENAI_CATALOGUE: tuple[ModelDefinition[OpenAIParams], ...] = (
    _openai_definition(
        "openai/gpt-image-2",
        "GPT Image 2",
        parameter_type=OpenAIParams,
    ),
    _openai_definition(
        "openai/gpt-image-1-mini",
        "GPT Image 1 Mini",
        parameter_type=OpenAIMiniParams,
        ratios=("1:1", "2:3", "3:2"),
    ),
)

OPENAI_MODELS: tuple[ModelSpec, ...] = tuple(definition.spec for definition in OPENAI_CATALOGUE)


class OpenAIProvider:
    """OpenAI image generation provider."""

    name = "openai"
    catalogue = OPENAI_CATALOGUE

    def __init__(
        self,
        client: httpx2.AsyncClient | None,
        client_factory: Callable[[], httpx2.AsyncClient] | None = None,
    ) -> None:
        self._client = client
        self._client_factory = client_factory

    @property
    def available(self) -> bool:
        return self._client is not None or self._client_factory is not None

    def _get_client(self) -> httpx2.AsyncClient:
        if self._client is None:
            if self._client_factory is None:
                raise ProviderError(
                    ErrorCode.CREDENTIAL_UNAVAILABLE,
                    "OpenAI API key not configured",
                )
            self._client = self._client_factory()
        return self._client

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:
        output_format = request.parameters.model_dump().get("output_format")
        if output_format:
            return f"image/{output_format}"
        return None

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        intent = request.request.intent
        params = request.request.parameters.model_dump(exclude_none=True)
        model_id = request.request.model.id.split("/", 1)[-1]

        if isinstance(intent, ImageCreateIntent) and not intent.references:
            return await self._generate_json(model_id, intent.prompt, params)
        return await self._generate_multipart(request)

    async def _generate_json(
        self,
        model_id: str,
        prompt: str,
        params: JsonObject,
    ) -> ProviderImage:
        client = self._get_client()
        payload = {"model": model_id, "prompt": prompt, **params}
        try:
            response = await client.post(
                f"{_OPENAI_BASE_URL}/images/generations",
                json=payload,
            )
            response.raise_for_status()
        except Exception as exc:
            raise self._map_error(exc) from exc

        return _decode_image_response(response.json())

    async def _generate_multipart(self, request: PreparedImageRequest) -> ProviderImage:
        client = self._get_client()
        intent = request.request.intent
        params = request.request.parameters.model_dump(exclude_none=True)

        files: list[tuple[str, tuple[str, bytes, str]]] = []
        if isinstance(intent, (ImageCreateIntent, ImageEditIntent)):
            files.extend(
                ("image[]", (media.image.filename, media.image.content, media.image.media_type))
                for media in request.media
            )

        form_data = {
            "model": request.request.model.id.split("/")[1]
            if "/" in request.request.model.id
            else request.request.model.id,
            "prompt": intent.prompt,
        }
        for key, value in params.items():
            form_data[key] = json.dumps(value) if not isinstance(value, str) else value

        try:
            response = await client.post(
                f"{_OPENAI_BASE_URL}/images/edits",
                data=form_data,
                files=files,
            )
            response.raise_for_status()
        except Exception as exc:
            raise self._map_error(exc) from exc

        return _decode_image_response(response.json())

    def _map_error(self, exc: Exception) -> PixgenError:
        from http import HTTPStatus

        import httpx2

        if isinstance(exc, httpx2.TimeoutException):
            return ProviderError(ErrorCode.TIMEOUT, "request timed out")
        if isinstance(exc, httpx2.ConnectError):
            return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "cannot connect to OpenAI")
        if isinstance(exc, httpx2.HTTPStatusError):
            status = exc.response.status_code

            match status:
                case HTTPStatus.UNAUTHORIZED | HTTPStatus.FORBIDDEN:
                    return ProviderError(ErrorCode.AUTHENTICATION_FAILED, "invalid API key")

                case HTTPStatus.NOT_FOUND:
                    return ProviderError(ErrorCode.MODEL_NOT_FOUND, "model not found")

                case HTTPStatus.TOO_MANY_REQUESTS:
                    return ProviderError(ErrorCode.RATE_LIMITED, "rate limit exceeded")

                case HTTPStatus.BAD_REQUEST:
                    body = exc.response.text.lower()
                    if "moderation" in body or "content_policy" in body:
                        return ProviderError(ErrorCode.CONTENT_REJECTED, "content rejected")
                    return ProviderError(ErrorCode.INVALID_REQUEST, "bad request")
                case _ if status >= 500:
                    return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "OpenAI server error")

                case _:
                    return ProviderError(ErrorCode.PROVIDER_FAILURE, "OpenAI request failed")

        return ProviderError(ErrorCode.PROVIDER_FAILURE, "unexpected OpenAI provider failure")


def _decode_image_response(payload: object) -> ProviderImage:
    """Validate and decode an OpenAI image response without exposing payload data."""
    try:
        response = _OpenAIImageResponse.model_validate(payload)
        image_bytes = base64.b64decode(response.data[0].b64_json, validate=True)
    except (ValidationError, ValueError, binascii.Error) as exc:
        raise ProviderError(
            ErrorCode.PROVIDER_FAILURE, "OpenAI returned an invalid image response"
        ) from exc
    if not image_bytes:
        raise ProviderError(ErrorCode.PROVIDER_FAILURE, "OpenAI returned an empty image")
    return ProviderImage(image_bytes, f"image/{response.output_format}")
