"""Gemini image generation adapter."""

from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from pixgen.core.definitions import ModelDefinition
from pixgen.core.errors import ErrorCode, PixgenError, ProviderError
from pixgen.core.models import (
    ImageOperation,
    MediaRole,
    MediaRoleSpec,
    ModelSpec,
)
from pixgen.core.parameters import ProviderParams
from pixgen.providers.base import PreparedImageRequest, ProviderImage

if TYPE_CHECKING:
    from collections.abc import Callable

    from google.genai import Client

    from pixgen.core.requests import ValidatedImageRequest

__all__: list[str] = [
    "GEMINI_CATALOGUE",
    "GEMINI_MODELS",
    "GeminiParams",
    "GeminiProvider",
]

type GeminiAspectRatio = Literal["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]
type ImageSize = Literal["1K", "2K", "4K"]


class GeminiParams(ProviderParams):
    """Validated parameters for Gemini image models."""

    aspect_ratio: GeminiAspectRatio | None = Field(
        default=None,
        description="Aspect ratio of generated image",
    )
    image_size: ImageSize | None = Field(
        default=None,
        description="Image size",
    )


class GeminiLiteParams(GeminiParams):
    """Parameters supported by the Gemini Flash Lite image model."""

    image_size: Literal["1K"] | None = Field(default=None, description="Image size")


_GEMINI_SHARED_RATIOS: dict[str, GeminiAspectRatio] = {
    "1:1": "1:1",
    "2:3": "2:3",
    "3:2": "3:2",
    "3:4": "3:4",
    "4:3": "4:3",
    "9:16": "9:16",
    "16:9": "16:9",
    "7:3": "21:9",
}


def _gemini_definition(
    model_id: str,
    display_name: str,
    *,
    max_refs: int,
    parameter_type: type[GeminiParams] = GeminiParams,
) -> ModelDefinition[GeminiParams]:
    """Define one Gemini model."""
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

    # Model specification for the Gemini image model.
    spec = ModelSpec(
        id=model_id,
        display_name=display_name,
        operations=frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT}),
        media={MediaRole.REFERENCE: ref_spec, MediaRole.IMAGE: image_spec},
        documentation_url="https://ai.google.dev/gemini-api/docs/image-generation",
        verified_at=date(2026, 9, 24),
    )

    return ModelDefinition[GeminiParams](
        spec=spec,
        parameter_type=parameter_type,
        defaults=parameter_type(),
        aspect_ratios={
            shared: {"aspect_ratio": native} for shared, native in _GEMINI_SHARED_RATIOS.items()
        },
    )


# Define the Gemini catalogue of model definitions.
GEMINI_CATALOGUE: tuple[ModelDefinition[GeminiParams], ...] = (
    _gemini_definition(
        "gemini/gemini-3.1-flash-image",
        "Gemini 3.1 Flash Image",
        max_refs=10,
    ),
    _gemini_definition(
        "gemini/gemini-3.1-flash-lite-image",
        "Gemini 3.1 Flash Lite Image",
        max_refs=14,
        parameter_type=GeminiLiteParams,
    ),
    _gemini_definition(
        "gemini/gemini-3-pro-image",
        "Gemini 3 Pro Image",
        max_refs=6,
    ),
)

# Extract the model specifications from the Gemini catalogue.
GEMINI_MODELS: tuple[ModelSpec, ...] = tuple(definition.spec for definition in GEMINI_CATALOGUE)


class GeminiProvider:
    """Gemini image generation provider."""

    name = "gemini"
    catalogue = GEMINI_CATALOGUE

    def __init__(
        self,
        client: Client | None,
        client_factory: Callable[[], Client] | None = None,
    ) -> None:
        self._client = client
        self._client_factory = client_factory

    @property
    def available(self) -> bool:
        return self._client is not None or self._client_factory is not None

    def _get_client(self) -> Client:
        if self._client is None:
            if self._client_factory is None:
                raise ProviderError(
                    ErrorCode.CREDENTIAL_UNAVAILABLE,
                    "Gemini API key not configured",
                )
            self._client = self._client_factory()
        return self._client

    async def aclose(self) -> None:
        """Close the async and sync transports; a later call recreates the client."""
        client = self._client
        if client is None:
            return
        if self._client_factory is not None:
            self._client = None
        try:
            await client.aio.aclose()
        finally:
            client.close()

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:  # noqa: ARG002
        return None

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        client = self._get_client()

        from google.genai import types

        intent = request.request.intent
        params = request.request.parameters.model_dump(exclude_none=True)
        model_id = (
            request.request.model.id.split("/")[1]
            if "/" in request.request.model.id
            else request.request.model.id
        )

        contents: list[types.PartUnionDict] = [intent.prompt]
        contents.extend(
            types.Part.from_bytes(
                data=media.image.content,
                mime_type=media.image.media_type,
            )
            for media in request.media
        )

        config = types.GenerateContentConfig.model_validate(
            {
                "response_modalities": ["IMAGE"],
                "image_config": types.ImageConfig.model_validate(params) if params else None,
            }
        )

        try:
            chat = client.aio.chats.create(model=model_id)
            response = await chat.send_message(
                message=contents,
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
        finish_name = getattr(finish_reason, "name", str(finish_reason).rsplit(".", 1)[-1])
        if finish_name in safety_reasons:
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
                    if "safety" in message or "prohibited" in message or "blocklist" in message:
                        return ProviderError(ErrorCode.CONTENT_REJECTED, "content rejected")
                    return ProviderError(ErrorCode.INVALID_REQUEST, "bad request")

        if isinstance(exc, errors.ServerError):
            return ProviderError(ErrorCode.PROVIDER_UNAVAILABLE, "Gemini server error")

        if "timeout" in str(exc).lower():
            return ProviderError(ErrorCode.TIMEOUT, "request timed out")

        return ProviderError(ErrorCode.PROVIDER_FAILURE, "unexpected Gemini provider failure")
