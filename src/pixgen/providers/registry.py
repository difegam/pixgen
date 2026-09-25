from __future__ import annotations

from typing import TYPE_CHECKING

from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from pixgen.core.models import ModelId, ModelSpec
    from pixgen.providers.base import ImageProvider

__all__: list[str] = [
    "ProviderRegistry",
]

type ModelMap = dict[ModelId, ImageProvider]


class ProviderRegistry:
    """Maps model IDs to providers and aggregates the catalog."""

    def __init__(self, providers: tuple[ImageProvider, ...]) -> None:
        self._providers = providers
        self._model_map: ModelMap = {
            spec.id: provider for provider in providers for spec in provider.models()
        }

    def models(self) -> tuple[ModelSpec, ...]:
        """Return all curated model specifications."""
        result: list[ModelSpec] = [
            model_spec for provider in self._providers for model_spec in provider.models()
        ]
        return tuple(result)

    def provider_for(self, model_id: ModelId) -> ImageProvider:
        """Return the provider for a model, raising if not found."""
        provider = self._model_map.get(model_id)
        if provider is None:
            raise PixgenError(
                ErrorCode.MODEL_NOT_FOUND,
                f"model {model_id!r} is not in the curated catalog",
            )
        return provider

    def get_model(self, model_id: ModelId) -> ModelSpec:
        """Return the model specification, raising if not found."""
        provider = self.provider_for(model_id)
        for spec in provider.models():
            if spec.id == model_id:
                return spec
        raise PixgenError(
            ErrorCode.MODEL_NOT_FOUND,
            f"model {model_id!r} is not in the curated catalog",
        )


# TODO: Implement a decorator for registering image providers
