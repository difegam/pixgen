"""Define shared and provider-owned image parameter models."""

from pydantic import BaseModel, ConfigDict, Field

from pixgen.core.aspect_ratio import AspectRatio

__all__: list[str] = ["ProviderParams", "SharedImageParams"]


class ProviderParams(BaseModel):
    """Base class for provider-owned native parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SharedImageParams(BaseModel):
    """Portable parameters accepted by multi-model image commands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aspect_ratio: AspectRatio | None = Field(
        default=None,
        description="Requested output aspect ratio in width:height form",
    )
