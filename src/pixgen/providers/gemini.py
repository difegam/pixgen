"""Gemini image generation adapter."""

from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import ConfigDict, Field, ValidationError

from pixgen.core.definitions import ModelDefinition, OperationDefinition, ProviderDefinition
from pixgen.core.errors import ErrorCode, PixgenError, ProviderError, validation_message
from pixgen.core.models import (
    ImageOperation,
    JsonObject,
    JsonSchema,
    MediaRole,
    MediaRoleSpec,
    ModelId,
    ModelSpec,
)
from pixgen.core.parameters import ProviderParams
from pixgen.core.requests import ImageIntent, ValidatedImageRequest
from pixgen.providers.base import PreparedImageRequest, ProviderImage

if TYPE_CHECKING:
    from collections.abc import Callable

    from google.genai import Client

__all__: list[str] = [
    "GEMINI_MODELS",
    "GeminiParams",
    "GeminiProvider",
]

type AspectRatio = Literal["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]
type ImageSize = Literal["1K", "2K", "4K"]


class GeminiParams(ProviderParams):
    """Validated parameters for Gemini image models."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aspect_ratio: AspectRatio | None = Field(
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


def _parameter_model(model: ModelId) -> type[GeminiParams]:
    """Return the parameter model for a curated Gemini model."""
    if model == "gemini/gemini-3.1-flash-lite-image":
        return GeminiLiteParams
    return GeminiParams


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

_GEMINI_SHARED_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "7:3")


def _gemini_operation(
    spec: ModelSpec,
    parameter_type: type[GeminiParams],
) -> OperationDefinition[GeminiParams]:
    """Build one Gemini operation definition."""
    return OperationDefinition[GeminiParams](
        parameter_type=parameter_type,
        defaults=parameter_type(),
        media=spec.media,
        aspect_ratios={
            ratio: {"aspect_ratio": "21:9" if ratio == "7:3" else ratio}
            for ratio in _GEMINI_SHARED_RATIOS
        },
    )


def _make_gemini_definitions() -> ProviderDefinition[ModelDefinition[GeminiParams]]:
    """Build the Gemini provider catalogue."""
    definitions: list[ModelDefinition[GeminiParams]] = []
    for spec in GEMINI_MODELS:
        parameter_type: type[GeminiParams] = (
            GeminiLiteParams if spec.id == "gemini/gemini-3.1-flash-lite-image" else GeminiParams
        )
        definitions.append(
            ModelDefinition[GeminiParams](
                spec=spec,
                operations={
                    operation: _gemini_operation(spec, parameter_type)
                    for operation in spec.operations
                },
            )
        )
    return ProviderDefinition[ModelDefinition[GeminiParams]](
        name="gemini",
        models=tuple(definitions),
    )


class GeminiProvider:
    """Gemini image generation provider."""

    name = "gemini"

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

    def models(self) -> tuple[ModelSpec, ...]:
        return GEMINI_MODELS

    def cli_factory(self) -> object:
        """Return the Gemini-owned CLI factory."""
        from pixgen.providers.gemini_cli import GeminiCliFactory

        return GeminiCliFactory()

    def definition_catalogue(self) -> ProviderDefinition[ModelDefinition[GeminiParams]]:
        """Return the composed Gemini model catalogue."""
        return _make_gemini_definitions()

    def definitions(self) -> tuple[ModelDefinition[GeminiParams], ...]:
        """Return composed Gemini model definitions."""
        return self.definition_catalogue().models

    def parameter_schema(
        self,
        model: ModelId,
        operation: ImageOperation,
    ) -> JsonSchema:
        definition = next(item for item in self.definitions() if item.spec.id == model)
        return definition.operations[operation].parameter_type.model_json_schema()

    def validate(
        self,
        *,
        intent: ImageIntent,
        model: ModelSpec,
    ) -> ValidatedImageRequest:
        try:
            params = _parameter_model(model.id).model_validate(intent.params)
        except ValidationError as exc:
            raise PixgenError(ErrorCode.INVALID_REQUEST, validation_message(exc)) from exc
        parameters: JsonObject = params.model_dump(exclude_none=True)
        return ValidatedImageRequest(
            intent=intent,
            model=model,
            parameters=parameters,
            native_parameters=params,
        )

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:  # noqa: ARG002
        return None

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        client = self._get_client()

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
