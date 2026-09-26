from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from pixgen.core.models import ImageOperation, JsonObject, MediaRole, ModelSpec

__all__: list[str] = [
    "ImageCreateIntent",
    "ImageEditIntent",
    "ImageIntent",
    "ValidatedImageRequest",
]


class ImageIntentBase(BaseModel):
    """Base for image generation intents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(min_length=3, description="Prompt for image generation")
    params: JsonObject = Field(default_factory=dict, description="Provider-neutral parameters")


class ImageCreateIntent(ImageIntentBase):
    """Intent to create an image from a prompt and optional references."""

    media_role: ClassVar[MediaRole] = MediaRole.REFERENCE

    operation: Literal[ImageOperation.IMAGE_CREATE] = ImageOperation.IMAGE_CREATE
    references: tuple[Path, ...] = Field(default=(), description="Ordered reference image paths")

    @property
    def input_paths(self) -> tuple[Path, ...]:
        return self.references


class ImageEditIntent(ImageIntentBase):
    """Intent to edit one or more source images."""

    media_role: ClassVar[MediaRole] = MediaRole.IMAGE

    operation: Literal[ImageOperation.IMAGE_EDIT] = ImageOperation.IMAGE_EDIT
    images: tuple[Path, ...] = Field(min_length=1, description="Ordered source image paths")

    @property
    def input_paths(self) -> tuple[Path, ...]:
        return self.images


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
