"""Provider protocol and internal data types."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pixgen.core.definitions import ModelDefinition
    from pixgen.core.models import MediaRole
    from pixgen.core.requests import ValidatedImageRequest
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
    """Generate images for the models in the provider's catalogue."""

    name: str

    @property
    def catalogue(self) -> tuple[ModelDefinition[Any], ...]:
        """Return the definitions of the models this provider generates with."""
        ...

    @property
    def available(self) -> bool:
        """Return whether the provider has credentials configured."""
        ...

    def declared_media_type(self, request: ValidatedImageRequest) -> str | None:
        """Return the declared output media type, or None if provider decides."""
        ...

    async def generate(self, request: PreparedImageRequest) -> ProviderImage:
        """Generate an image from a prepared request."""
        ...
