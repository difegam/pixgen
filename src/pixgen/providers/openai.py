"""OpenAI image generation adapter."""

import base64
import json
from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from pixgen.core.errors import ErrorCode, PixgenError, ProviderError
from pixgen.core.models import (
    ImageOperation,
    JsonObject,
    JsonSchema,
    MediaRole,
    MediaRoleSpec,
    ModelId,
    ModelSpec,
)
from pixgen.core.requests import (
    ImageCreateIntent,
    ImageEditIntent,
    ImageIntent,
    ValidatedImageRequest,
)
from pixgen.providers.base import (
    PreparedImageRequest,
    ProviderImage,
)

if TYPE_CHECKING:
    import httpx2

__all__: list[str] = [
    "OPENAI_MODELS",
    "OpenAIProvider",
]

_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIParams(BaseModel):
    """Validated parameters for OpenAI image models."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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
    output_compression: int | None = Field(
        default=None, ge=0, le=100, description="Compression level for jpeg/webp"
    )
    moderation: Literal["auto", "low"] | None = Field(
        default=None, description="Content moderation level"
    )


def _make_openai_spec(
    model_id: str,
    display_name: str,
) -> ModelSpec:
    """Create an OpenAI model specification."""
    media_spec = MediaRoleSpec(
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
    return ModelSpec(
        id=model_id,
        display_name=display_name,
        operations=frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT}),
        media={MediaRole.REFERENCE: media_spec, MediaRole.IMAGE: image_spec},
        documentation_url="https://platform.openai.com/docs/guides/images",
        verified_at=date(2026, 9, 24),
    )


OPENAI_MODELS: tuple[ModelSpec, ...] = (
    _make_openai_spec("openai/gpt-image-2", "GPT Image 2"),
    _make_openai_spec("openai/gpt-image-1-mini", "GPT Image 1 Mini"),
)


class OpenAIProvider:
    """OpenAI image generation provider."""

    name = "openai"

    def __init__(self, client: httpx2.AsyncClient | None) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client is not None

    def models(self) -> tuple[ModelSpec, ...]:
        return OPENAI_MODELS

    def parameter_schema(
        self,
        model: ModelId,  # noqa: ARG002
        operation: ImageOperation,  # noqa: ARG002
    ) -> JsonSchema:
        return OpenAIParams.model_json_schema()

    def validate(
        self,
        *,
        intent: ImageIntent,
        model: ModelSpec,
    ) -> ValidatedImageRequest:
        params = OpenAIParams.model_validate(intent.params)
        parameters: JsonObject = params.model_dump(exclude_none=True)
        return ValidatedImageRequest(intent=intent, model=model, parameters=parameters)

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:
        output_format = request.parameters.get("output_format")
        if output_format:
            return f"image/{output_format}"
        return None

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        if self._client is None:
            raise ProviderError(
                ErrorCode.CREDENTIAL_UNAVAILABLE,
                "OpenAI API key not configured",
            )

        intent = request.request.intent
        params = request.request.parameters
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
        if self._client is None:
            raise ProviderError(ErrorCode.CREDENTIAL_UNAVAILABLE, "OpenAI API key not configured")
        payload = {"model": model_id, "prompt": prompt, **params}
        try:
            response = await self._client.post(
                f"{_OPENAI_BASE_URL}/images/generations",
                json=payload,
            )
            response.raise_for_status()
        except Exception as exc:
            raise self._map_error(exc) from exc

        data = response.json()
        b64_data = data["data"][0]["b64_json"]
        image_bytes = base64.b64decode(b64_data)
        output_format = data.get("output_format", "png")
        return ProviderImage(image_bytes, f"image/{output_format}")

    async def _generate_multipart(self, request: PreparedImageRequest) -> ProviderImage:
        if self._client is None:
            raise ProviderError(ErrorCode.CREDENTIAL_UNAVAILABLE, "OpenAI API key not configured")
        intent = request.request.intent
        params = request.request.parameters

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
            response = await self._client.post(
                f"{_OPENAI_BASE_URL}/images/edits",
                data=form_data,
                files=files,
            )
            response.raise_for_status()
        except Exception as exc:
            raise self._map_error(exc) from exc

        data = response.json()
        b64_data = data["data"][0]["b64_json"]
        image_bytes = base64.b64decode(b64_data)
        output_format = data.get("output_format", "png")
        return ProviderImage(image_bytes, f"image/{output_format}")

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
                    body = exc.response.text
                    if "moderation" in body.lower() or "content_policy" in body.lower():
                        return ProviderError(ErrorCode.CONTENT_REJECTED, "content rejected")
                    return ProviderError(ErrorCode.INVALID_REQUEST, f"bad request: {body[:200]}")
                case _ if status >= 500:
                    return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "OpenAI server error")

                case _:
                    return ProviderError(ErrorCode.AUTHENTICATION_FAILED, "invalid API key")

        return ProviderError(ErrorCode.PROVIDER_FAILURE, f"unexpected error: {exc}")
