from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, model_validator

from pixgen.core.models import ImageOperation, MediaRole, ModelSpec
from pixgen.core.parameters import ProviderParams, SharedImageParams

__all__: list[str] = [
    "ImageCreateIntent",
    "ImageEditIntent",
    "ImageIntent",
    "NativeSelection",
    "ParameterSelection",
    "SharedSelection",
    "ValidatedImageRequest",
]


class SharedSelection(BaseModel):
    """Selection and shared parameters for one multi-model invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    models: tuple[str, ...] | None = None
    parameters: SharedImageParams = Field(default_factory=SharedImageParams)


class NativeSelection(BaseModel):
    """Selection and native parameters for one provider invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    parameters: SerializeAsAny[ProviderParams]


type ParameterSelection = SharedSelection | NativeSelection


class ImageIntentBase(BaseModel):
    """Base for image generation intents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(min_length=1, description="Prompt for image generation")

    @model_validator(mode="after")
    def _validate_prompt(self) -> Self:
        if not self.prompt.strip():
            raise ValueError("prompt must contain a non-whitespace character")
        return self


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
    parameters: SerializeAsAny[ProviderParams] = Field(
        description="Native parameters validated against the selected model"
    )
