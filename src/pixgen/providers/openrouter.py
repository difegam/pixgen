"""Provide OpenRouter's curated image models and generation adapter."""

import base64
from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from pixgen.core.definitions import ModelDefinition
from pixgen.core.errors import ErrorCode, PixgenError, ProviderError
from pixgen.core.models import ImageOperation, MediaRole, MediaRoleSpec, ModelSpec
from pixgen.core.parameters import ProviderParams
from pixgen.providers.http import decode_base64_image

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx2

    from pixgen.core.requests import ValidatedImageRequest
    from pixgen.providers.base import PreparedImageRequest, ProviderImage

__all__: list[str] = [
    "OPENROUTER_CATALOGUE",
    "OpenRouterGPTImageParams",
    "OpenRouterGeminiParams",
    "OpenRouterProvider",
]

_GEMINI_ASPECT_RATIOS: tuple[str, ...] = (
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
    "8:1",
    "9:16",
    "16:9",
    "21:9",
)
_GPT_ASPECT_RATIOS: tuple[str, ...] = (
    "1:1",
    "3:2",
    "2:3",
    "4:3",
    "3:4",
    "16:9",
    "9:16",
    "21:9",
)


type GeminiAspectRatio = Literal[
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
    "8:1",
    "9:16",
    "16:9",
    "21:9",
]
type GeminiResolution = Literal["512", "1K", "2K", "4K"]
type GPTAspectRatio = Literal[
    "1:1",
    "3:2",
    "2:3",
    "4:3",
    "3:4",
    "16:9",
    "9:16",
    "21:9",
    "auto",
]


class OpenRouterGeminiParams(ProviderParams):
    """Validated parameters for OpenRouter's Gemini image model."""

    aspect_ratio: GeminiAspectRatio | None = Field(
        default=None,
        description="Aspect ratio of generated image",
    )
    resolution: GeminiResolution | None = Field(default=None, description="Image resolution tier")


class OpenRouterGPTImageParams(ProviderParams):
    """Validated parameters for OpenRouter's GPT Image model."""

    aspect_ratio: GPTAspectRatio | None = Field(
        default=None,
        description="Aspect ratio of generated image",
    )
    quality: Literal["auto", "low", "medium", "high", "xhigh", "max"] | None = Field(
        default=None,
        description="Generation quality",
    )
    background: Literal["auto", "transparent", "opaque"] | None = Field(
        default=None,
        description="Background type",
    )
    output_compression: StrictInt | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Output compression level",
    )


def _definition(
    model_id: str,
    display_name: str,
    *,
    parameter_type: type[ProviderParams],
    operations: frozenset[ImageOperation],
    max_references: int,
    aspect_ratios: tuple[str, ...] = (),
) -> ModelDefinition:
    """Define a curated OpenRouter image model."""
    media = {
        MediaRole.IMAGE: MediaRoleSpec(
            minimum=1,
            maximum=max(max_references, 1),
            formats=frozenset({"png", "jpeg", "webp"}),
            max_bytes=52_428_800,
        )
    }
    if ImageOperation.IMAGE_EDIT in operations:
        media[MediaRole.REFERENCE] = MediaRoleSpec(
            minimum=0,
            maximum=max_references,
            formats=frozenset({"png", "jpeg", "webp"}),
            max_bytes=52_428_800,
        )

    spec = ModelSpec(
        id=model_id,
        display_name=display_name,
        operations=operations,
        media=media,
        documentation_url="https://openrouter.ai/docs/guides/overview/multimodal/image-generation",
        verified_at=date(2026, 10, 1),
    )
    return ModelDefinition(
        spec=spec,
        parameter_type=parameter_type,
        defaults=parameter_type(),
        aspect_ratios={ratio: {"aspect_ratio": ratio} for ratio in aspect_ratios},
    )


_CREATE_AND_EDIT = frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT})
_CREATE_ONLY = frozenset({ImageOperation.IMAGE_CREATE})

OPENROUTER_CATALOGUE: tuple[ModelDefinition, ...] = (
    _definition(
        "openrouter/google/gemini-3.1-flash-image",
        "Gemini 3.1 Flash Image (OpenRouter)",
        parameter_type=OpenRouterGeminiParams,
        operations=_CREATE_AND_EDIT,
        max_references=14,
        aspect_ratios=_GEMINI_ASPECT_RATIOS,
    ),
    _definition(
        "openrouter/meta/muse-image",
        "Muse Image (OpenRouter)",
        parameter_type=ProviderParams,
        operations=_CREATE_ONLY,
        max_references=0,
    ),
    _definition(
        "openrouter/openai/gpt-image-2.5-sunburst",
        "GPT Image 2.5 Sunburst (OpenRouter)",
        parameter_type=OpenRouterGPTImageParams,
        operations=_CREATE_AND_EDIT,
        max_references=16,
        aspect_ratios=_GPT_ASPECT_RATIOS,
    ),
)


class _OpenRouterImageItem(BaseModel):
    """Validate one image item from OpenRouter's buffered response."""

    model_config = ConfigDict(extra="allow")

    b64_json: str
    media_type: str | None = None


class _OpenRouterImageResponse(BaseModel):
    """Validate the image data envelope from OpenRouter."""

    model_config = ConfigDict(extra="allow")

    data: tuple[_OpenRouterImageItem, ...] = Field(min_length=1)


class OpenRouterProvider:
    """OpenRouter's buffered image generation provider."""

    name = "openrouter"
    catalogue = OPENROUTER_CATALOGUE

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

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:  # noqa: ARG002
        return None

    def _get_client(self) -> httpx2.AsyncClient:
        if self._client is None:
            if self._client_factory is None:
                raise ProviderError(
                    ErrorCode.CREDENTIAL_UNAVAILABLE,
                    "OpenRouter API key not configured",
                )
            self._client = self._client_factory()
        return self._client

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        client = self._get_client()
        intent = request.request.intent
        payload: dict[str, object] = {
            "model": request.request.model.model,
            "prompt": intent.prompt,
            **request.request.parameters.model_dump(exclude_none=True),
        }
        if request.media:
            payload["input_references"] = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            f"data:{media.image.media_type};base64,"
                            f"{base64.b64encode(media.image.content).decode('ascii')}"
                        )
                    },
                }
                for media in request.media
            ]

        try:
            response = await client.post("images", json=payload)
            response.raise_for_status()
            response_payload = response.json()
        except Exception as exc:
            raise self._map_error(exc) from exc

        return _decode_image_response(response_payload)

    def _map_error(self, exc: Exception) -> PixgenError:
        from http import HTTPStatus

        import httpx2

        if isinstance(exc, httpx2.TimeoutException):
            return ProviderError(ErrorCode.TIMEOUT, "request timed out")
        if isinstance(exc, httpx2.ConnectError):
            return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "cannot connect to OpenRouter")
        if isinstance(exc, httpx2.HTTPStatusError):
            status = exc.response.status_code
            status_errors: dict[int, tuple[ErrorCode, str]] = {
                HTTPStatus.UNAUTHORIZED: (ErrorCode.AUTHENTICATION_FAILED, "invalid API key"),
                HTTPStatus.FORBIDDEN: (ErrorCode.AUTHENTICATION_FAILED, "invalid API key"),
                HTTPStatus.NOT_FOUND: (ErrorCode.MODEL_NOT_FOUND, "model not found"),
                HTTPStatus.TOO_MANY_REQUESTS: (ErrorCode.RATE_LIMITED, "rate limit exceeded"),
            }
            if mapped_error := status_errors.get(status):
                return ProviderError(*mapped_error)
            if status >= 500:
                return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "OpenRouter server error")
            if 400 <= status < 500:
                body = exc.response.text.lower()
                markers = ("moderation", "content_policy", "content policy", "safety")
                if any(marker in body for marker in markers):
                    return ProviderError(ErrorCode.CONTENT_REJECTED, "content rejected")
                return ProviderError(ErrorCode.INVALID_REQUEST, "bad request")

        if isinstance(exc, httpx2.RequestError):
            return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "OpenRouter request failed")
        return ProviderError(ErrorCode.PROVIDER_FAILURE, "unexpected OpenRouter provider failure")


def _decode_image_response(payload: object) -> ProviderImage:
    """Validate the OpenRouter response envelope and decode its first image."""
    try:
        response = _OpenRouterImageResponse.model_validate(payload)
    except ValidationError as exc:
        raise ProviderError(
            ErrorCode.PROVIDER_FAILURE,
            "OpenRouter returned an invalid image response",
        ) from exc

    image = response.data[0]
    return decode_base64_image(
        image.b64_json,
        media_type=image.media_type or "image/png",
        provider_name="OpenRouter",
    )
