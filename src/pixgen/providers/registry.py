from typing import TYPE_CHECKING

from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from pixgen.core.models import ImageOperation, ModelId, ModelSpec
    from pixgen.providers.base import ImageProvider

__all__: list[str] = [
    "ProviderRegistry",
]

type ModelMap = dict[ModelId, ImageProvider]


class ProviderRegistry:
    """Maps model IDs to providers and aggregates the catalog."""

    def __init__(self, providers: tuple[ImageProvider, ...]) -> None:
        self._providers = providers
        provider_names: set[str] = set()
        model_map: ModelMap = {}
        for provider in providers:
            if provider.name in provider_names:
                raise ValueError(f"duplicate provider name: {provider.name!r}")
            provider_names.add(provider.name)
            expected_prefix = f"{provider.name}/"
            for spec in provider.models():
                if not spec.id.startswith(expected_prefix):
                    raise ValueError(
                        f"model {spec.id!r} is not owned by provider {provider.name!r}"
                    )
                if spec.id in model_map:
                    raise ValueError(f"duplicate model id: {spec.id!r}")
                model_map[spec.id] = provider
        self._model_map = model_map

    def providers(self) -> tuple[ImageProvider, ...]:
        """Return the registered providers in composition order."""
        return self._providers

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

    def shared_aspect_ratios(
        self,
        model_id: ModelId,
        operation: ImageOperation,
    ) -> tuple[str, ...]:
        """Return canonical shared ratios declared by one model operation."""
        provider = self.provider_for(model_id)
        return provider.shared_aspect_ratios(model_id, operation)
