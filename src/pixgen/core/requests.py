from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from pixgen.core.models import MediaReference, ModelId, Operation

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class RequestBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt: str = Field(min_length=1)
    model: ModelId
    params: dict[str, JsonValue] = Field(default_factory=dict)


class ImageRequestBase(RequestBase):
    aspect_ratio: str | None = None
    resolution: str | None = None
    count: int = Field(default=1, ge=1)


class ImageCreateRequest(ImageRequestBase):
    operation: Literal[Operation.IMAGE_CREATE] = Operation.IMAGE_CREATE
    references: tuple[MediaReference, ...] = ()


class ImageEditRequest(ImageRequestBase):
    operation: Literal[Operation.IMAGE_EDIT] = Operation.IMAGE_EDIT
    images: tuple[MediaReference, ...] = ()
    mask: MediaReference | None = None


class VideoCreateRequest(RequestBase):
    operation: Literal[Operation.VIDEO_CREATE] = Operation.VIDEO_CREATE
    start_frame: MediaReference | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | None = None


# Discriminated union for generation requests
type GenerationRequest = Annotated[
    ImageCreateRequest | ImageEditRequest | VideoCreateRequest,
    Field(discriminator="operation"),
]
