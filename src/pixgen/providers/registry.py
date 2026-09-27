from typing import TYPE_CHECKING

from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from pixgen.cli.contracts import ProviderCliFactory
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
        definitions = getattr(provider, "definitions", None)
        if definitions is None:
            return ()
        for definition in definitions():
            if definition.spec.id == model_id:
                operation_definition = definition.operations.get(operation)
                if operation_definition is None:
                    return ()
                return tuple(sorted(operation_definition.aspect_ratios))
        return ()

    def cli_factories(self) -> tuple[ProviderCliFactory, ...]:
        """Return provider-owned CLI factories without importing providers here."""
        factories: list[ProviderCliFactory] = []
        factory_names: set[str] = set()
        for provider in self._providers:
            factory_builder = getattr(provider, "cli_factory", None)
            if factory_builder is None:
                raise ValueError(f"provider {provider.name!r} does not expose a CLI factory")
            factory = factory_builder()
            if factory.name in factory_names:
                raise ValueError(f"duplicate provider CLI name: {factory.name!r}")
            if factory.name != provider.name:
                raise ValueError(
                    f"CLI factory {factory.name!r} does not match provider {provider.name!r}"
                )
            supported_operations = {
                operation for spec in provider.models() for operation in spec.operations
            }
            unsupported_operations = factory.operations - supported_operations
            if unsupported_operations:
                raise ValueError(
                    f"CLI factory {factory.name!r} declares unsupported operations: "
                    f"{sorted(operation.value for operation in unsupported_operations)!r}"
                )
            factory_names.add(factory.name)
            factories.append(factory)
        return tuple(factories)


# TODO: Implement a decorator for registering image providers
