from enum import StrEnum

from pydantic import BaseModel, Field, Json

from pixgen.core.models import MediaReference, ModelId


class Operation(StrEnum):
    IMAGE_CREATE = "image-create"
    IMAGE_EDIT = "image-edit"
    VIDEO_CREATE = "video-create"


class RequestBase(BaseModel):
    prompt: str
    model: ModelId
    aspect_ratio: str | None = None
    resolution: str | None = None
    count: int = 1
    params: dict[str, Json] = Field(default_factory=dict)


class ImageCreateRequest(RequestBase):
    operation: Operation = Operation.IMAGE_CREATE
    references: tuple[MediaReference, ...] = ()


class ImageEditRequest(RequestBase):
    operation: Operation = Operation.IMAGE_EDIT
    images: tuple[MediaReference, ...]
    mask: MediaReference | None = None


class VideoCreateRequest(RequestBase):
    operation: Operation = Operation.VIDEO_CREATE
    prompt: str
    model: ModelId
    start_frame: MediaReference | None = None
    duration: int | None = None


type GenerationRequest = ImageCreateRequest | ImageEditRequest | VideoCreateRequest
