from typing import TYPE_CHECKING, Protocol

from pydantic import AnyHttpUrl, BaseModel, ConfigDict

from pixgen.core.errors import ErrorCode

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pixgen.core.models import ModelSpec, ProviderGeneration
    from pixgen.core.requests import GenerationRequest


class ProviderMedia(BaseModel):
    model_config = ConfigDict(frozen=True)

    media_type: str
    data: bytes | None = None
    fetch_url: AnyHttpUrl | None = None


class ProviderUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    image_count: int | None = None


class ProviderError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    retryable: bool = False


class ProviderGeneration(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: GenerationStatus
    provider_job_id: str | None = None
    media: tuple[ProviderMedia, ...] = ()
    usage: ProviderUsage | None = None
    error: ProviderError | None = None


class Provider(Protocol):
    name: str

    def list_models(self) -> Sequence: ...
    def validate_params(
        self,
        request: GenerationRequest,
        spec: ModelSpec,
    ) -> list: ...

    async def submit(self, request: GenerationRequest) -> ProviderGeneration: ...
    async def get(self, provider_job_id: str) -> ProviderGeneration: ...
    async def cancel(self, provider_job_id: str) -> ProviderGeneration: ...
