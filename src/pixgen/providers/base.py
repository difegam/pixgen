"""Provider protocol and internal data types."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pixgen.core.models import (
        ImageOperation,
        JsonObject,
        JsonSchema,
        MediaRole,
        ModelId,
        ModelSpec,
    )
    from pixgen.core.parameters import SharedImageParams
    from pixgen.core.requests import ImageIntent, ValidatedImageRequest
    from pixgen.images.models import LocalImage

__all__: list[str] = [
    "ImageProvider",
    "PreparedImageRequest",
    "PreparedMedia",
    "ProviderImage",
]


@dataclass(frozen=True, slots=True)
class PreparedMedia:
    """A loaded image with its intended role."""

    role: MediaRole
    image: LocalImage


@dataclass(frozen=True, slots=True)
class PreparedImageRequest:
    """A validated request with loaded media."""

    request: ValidatedImageRequest
    media: tuple[PreparedMedia, ...]


@dataclass(frozen=True, slots=True)
class ProviderImage:
    """Binary image result from a provider."""

    data: bytes
    media_type: str


@runtime_checkable
class ImageProvider(Protocol):
    """Structural interface for image generation providers."""

    name: str

    @property
    def available(self) -> bool:
        """Return whether the provider has credentials configured."""
        ...

    def models(self) -> tuple[ModelSpec, ...]:
        """Return the curated model specifications."""
        ...

    def parameter_schema(
        self,
        model: ModelId,
        operation: ImageOperation,
    ) -> JsonSchema:
        """Return the JSON Schema for a model's parameters."""
        ...

    def resolve_shared_parameters(
        self,
        model: ModelId,
        operation: ImageOperation,
        shared: SharedImageParams,
    ) -> JsonObject:
        """Resolve portable parameters for one model operation."""
        ...

    def shared_aspect_ratios(
        self,
        model: ModelId,
        operation: ImageOperation,
    ) -> tuple[str, ...]:
        """Return portable aspect ratios supported by one model operation."""
        ...

    def validate(
        self,
        *,
        intent: ImageIntent,
        model: ModelSpec,
    ) -> ValidatedImageRequest:
        """Validate an intent against a model and return a validated request."""
        ...

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:
        """Return the declared output media type, or None if provider decides."""
        ...

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        """Generate an image from a prepared request."""
        ...
