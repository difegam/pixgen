"""Gemini image generation adapter."""

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
from pixgen.core.requests import ImageIntent, ValidatedImageRequest
from pixgen.providers.base import PreparedImageRequest, ProviderImage

if TYPE_CHECKING:
    from google.genai import Client

__all__: list[str] = [
    "GEMINI_MODELS",
    "GeminiProvider",
]


class GeminiParams(BaseModel):
    """Validated parameters for Gemini image models."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aspect_ratio: Literal["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"] | None = Field(
        default=None, description="Aspect ratio of generated image"
    )
    image_size: Literal["1K", "2K", "4K"] | None = Field(default=None, description="Image size")


def _make_gemini_spec(
    model_id: str,
    display_name: str,
    max_refs: int,
) -> ModelSpec:
    """Create a Gemini model specification."""
    ref_spec = MediaRoleSpec(
        minimum=0,
        maximum=max_refs,
        formats=frozenset({"png", "jpeg", "webp"}),
        max_bytes=20_971_520,
    )
    image_spec = MediaRoleSpec(
        minimum=1,
        maximum=max_refs,
        formats=frozenset({"png", "jpeg", "webp"}),
        max_bytes=20_971_520,
    )
    return ModelSpec(
        id=model_id,
        display_name=display_name,
        operations=frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT}),
        media={MediaRole.REFERENCE: ref_spec, MediaRole.IMAGE: image_spec},
        documentation_url="https://ai.google.dev/gemini-api/docs/image-generation",
        verified_at=date(2026, 9, 24),
    )


GEMINI_MODELS: tuple[ModelSpec, ...] = (
    _make_gemini_spec("gemini/gemini-3.1-flash-image", "Gemini 3.1 Flash Image", max_refs=10),
    _make_gemini_spec(
        "gemini/gemini-3.1-flash-lite-image",
        "Gemini 3.1 Flash Lite Image",
        max_refs=14,
    ),
    _make_gemini_spec("gemini/gemini-3-pro-image", "Gemini 3 Pro Image", max_refs=6),
)

_GEMINI_IMAGE_SIZES: dict[ModelId, tuple[str, ...]] = {
    "gemini/gemini-3.1-flash-image": ("1K", "2K", "4K"),
    "gemini/gemini-3.1-flash-lite-image": ("1K",),
    "gemini/gemini-3-pro-image": ("1K", "2K", "4K"),
}


class GeminiProvider:
    """Gemini image generation provider."""

    name = "gemini"

    def __init__(self, client: Client | None) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client is not None

    def models(self) -> tuple[ModelSpec, ...]:
        return GEMINI_MODELS

    def parameter_schema(
        self,
        model: ModelId,
        operation: ImageOperation,  # noqa: ARG002
    ) -> JsonSchema:
        schema = GeminiParams.model_json_schema()
        schema["properties"]["image_size"]["enum"] = list(
            _GEMINI_IMAGE_SIZES.get(model, ("1K", "2K", "4K"))
        )
        return schema

    def validate(
        self,
        *,
        intent: ImageIntent,
        model: ModelSpec,
    ) -> ValidatedImageRequest:
        params = GeminiParams.model_validate(intent.params)
        if model.id == "gemini/gemini-3.1-flash-lite-image" and params.image_size not in {
            None,
            "1K",
        }:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                "Gemini Flash Lite only supports image_size='1K'",
            )
        parameters: JsonObject = params.model_dump(exclude_none=True)
        return ValidatedImageRequest(intent=intent, model=model, parameters=parameters)

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:  # noqa: ARG002
        return None

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        if self._client is None:
            raise ProviderError(
                ErrorCode.CREDENTIAL_UNAVAILABLE,
                "Gemini API key not configured",
            )

        from google.genai import types

        intent = request.request.intent
        params = request.request.parameters
        model_id = (
            request.request.model.id.split("/")[1]
            if "/" in request.request.model.id
            else request.request.model.id
        )

        contents: list[types.Content | types.Part | str] = [intent.prompt]
        contents.extend(
            types.Part.from_bytes(
                data=media.image.content,
                mime_type=media.image.media_type,
            )
            for media in request.media
        )

        config_kwargs: dict = {"response_modalities": ["IMAGE"]}
        if params:
            image_config_kwargs: dict = {}
            if "aspect_ratio" in params:
                image_config_kwargs["aspect_ratio"] = params["aspect_ratio"]
            if "image_size" in params:
                image_config_kwargs["image_size"] = params["image_size"]
            if image_config_kwargs:
                config_kwargs["image_config"] = types.ImageConfig(**image_config_kwargs)

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = await self._client.aio.models.generate_content(
                model=model_id,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise self._map_error(exc) from exc

        parts = response.parts or []
        for part in parts:
            if part.inline_data is not None and part.inline_data.data is not None:
                return ProviderImage(
                    part.inline_data.data,
                    part.inline_data.mime_type or "image/png",
                )

        finish_reason = response.candidates[0].finish_reason if response.candidates else None
        safety_reasons = {
            "SAFETY",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "IMAGE_SAFETY",
            "IMAGE_PROHIBITED_CONTENT",
        }
        if finish_reason and str(finish_reason) in safety_reasons:
            raise ProviderError(ErrorCode.CONTENT_REJECTED, "content rejected by safety filter")

        raise ProviderError(ErrorCode.PROVIDER_FAILURE, "no image in response")

    def _map_error(self, exc: Exception) -> PixgenError:
        from http import HTTPStatus

        from google.genai import errors

        if isinstance(exc, errors.ClientError):
            match exc.code:
                case HTTPStatus.UNAUTHORIZED | HTTPStatus.FORBIDDEN:
                    return ProviderError(ErrorCode.AUTHENTICATION_FAILED, "invalid API key")

                case HTTPStatus.NOT_FOUND:
                    return ProviderError(ErrorCode.MODEL_NOT_FOUND, "model not found")

                case HTTPStatus.TOO_MANY_REQUESTS:
                    return ProviderError(ErrorCode.RATE_LIMITED, "rate limit exceeded")

                case HTTPStatus.BAD_REQUEST:
                    message = str(exc).lower()
                    if "safety" in message or "content" in message:
                        return ProviderError(ErrorCode.CONTENT_REJECTED, "content rejected")
                    return ProviderError(ErrorCode.INVALID_REQUEST, f"bad request: {exc}")

        if isinstance(exc, errors.ServerError):
            return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "Gemini server error")

        if "timeout" in str(exc).lower():
            return ProviderError(ErrorCode.TIMEOUT, "request timed out")

        return ProviderError(ErrorCode.PROVIDER_FAILURE, f"unexpected error: {exc}")
