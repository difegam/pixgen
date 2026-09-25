"""Define image intent and validated request types."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from pixgen.core.models import ImageOperation, JsonObject, ModelSpec

__all__: list[str] = [
    "ImageCreateIntent",
    "ImageEditIntent",
    "ImageIntent",
    "ValidatedImageRequest",
]


class ImageIntentBase(BaseModel):
    """Base for image generation intents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(min_length=1, description="The text prompt for generation")
    params: JsonObject = Field(default_factory=dict, description="Provider-neutral parameters")


class ImageCreateIntent(ImageIntentBase):
    """Intent to create an image from a prompt and optional references."""

    operation: Literal[ImageOperation.IMAGE_CREATE] = ImageOperation.IMAGE_CREATE
    references: tuple[Path, ...] = Field(default=(), description="Ordered reference image paths")


class ImageEditIntent(ImageIntentBase):
    """Intent to edit one or more source images."""

    operation: Literal[ImageOperation.IMAGE_EDIT] = ImageOperation.IMAGE_EDIT
    images: tuple[Path, ...] = Field(min_length=1, description="Ordered source image paths")


type ImageIntent = Annotated[
    ImageCreateIntent | ImageEditIntent,
    Field(discriminator="operation"),
]


class ValidatedImageRequest(BaseModel):
    """A validated intent paired with a curated model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: ImageIntent = Field(description="The caller's intent")
    model: ModelSpec = Field(description="The selected curated model")
    parameters: JsonObject = Field(description="Validated parameters for the model")
