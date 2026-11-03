"""Index provider catalogues and answer model catalogue questions."""

import asyncio
import logging
from typing import TYPE_CHECKING

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.requests import ValidatedImageRequest

if TYPE_CHECKING:
    from pixgen.core.definitions import ModelDefinition
    from pixgen.core.models import ImageOperation, JsonSchema, ModelId, ModelSpec
    from pixgen.core.parameters import ProviderParams, SharedImageParams
    from pixgen.core.requests import ImageIntent
    from pixgen.providers.base import ImageProvider

__all__: list[str] = [
    "ProviderRegistry",
]

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Map model IDs to their definitions and providers."""

    def __init__(self, providers: tuple[ImageProvider, ...]) -> None:
        self._providers = providers
        provider_names: set[str] = set()
        entries: dict[ModelId, tuple[ModelDefinition, ImageProvider]] = {}
        for provider in providers:
            if provider.name in provider_names:
                raise ValueError(f"duplicate provider name: {provider.name!r}")
            provider_names.add(provider.name)
            expected_prefix = f"{provider.name}/"
            for definition in provider.catalogue:
                model_id = definition.spec.id
                if not model_id.startswith(expected_prefix):
                    raise ValueError(
                        f"model {model_id!r} is not owned by provider {provider.name!r}"
                    )
                if model_id in entries:
                    raise ValueError(f"duplicate model id: {model_id!r}")
                entries[model_id] = (definition, provider)
        self._entries = entries

    def providers(self) -> tuple[ImageProvider, ...]:
        """Return the registered providers in composition order."""
        return self._providers

    async def aclose(self) -> None:
        """Close every provider's client, logging failures instead of raising."""
        outcomes = await asyncio.gather(
            *(provider.aclose() for provider in self._providers),
            return_exceptions=True,
        )
        for provider, outcome in zip(self._providers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                # Type only: provider errors can echo prompts or response bodies.
                logger.warning(
                    "failed to close %s client: %s", provider.name, type(outcome).__name__
                )

    def models(self) -> tuple[ModelSpec, ...]:
        """Return all curated model specifications in composition order."""
        return tuple(definition.spec for definition, _ in self._entries.values())

    def provider_for(self, model_id: ModelId) -> ImageProvider:
        """Return the provider for a model, raising if not found."""
        return self._entry(model_id)[1]

    def get_model(self, model_id: ModelId) -> ModelSpec:
        """Return the model specification, raising if not found."""
        return self._entry(model_id)[0].spec

    def parameter_schema(self, model_id: ModelId, operation: ImageOperation) -> JsonSchema:
        """Return the JSON Schema of a model's native parameters for one operation."""
        return self._definition(model_id, operation).parameter_type.model_json_schema()

    def shared_aspect_ratios(
        self,
        model_id: ModelId,
        operation: ImageOperation,
    ) -> tuple[str, ...]:
        """Return canonical shared ratios a model supports for one operation."""
        return tuple(sorted(self._definition(model_id, operation).aspect_ratios))

    def validate(
        self,
        *,
        intent: ImageIntent,
        model_id: ModelId,
        parameters: SharedImageParams | ProviderParams | None = None,
    ) -> ValidatedImageRequest:
        """Resolve parameters against a model and return a validated request.

        Raises:
            PixgenError: If the model is unknown, does not support the intent's operation,
                or the parameters fall outside the model's native parameter type.
        """
        definition = self._definition(model_id, intent.operation)
        return ValidatedImageRequest(
            intent=intent,
            model=definition.spec,
            parameters=definition.resolve_parameters(parameters),
        )

    def _entry(self, model_id: ModelId) -> tuple[ModelDefinition, ImageProvider]:
        entry = self._entries.get(model_id)
        if entry is None:
            raise PixgenError(
                ErrorCode.MODEL_NOT_FOUND,
                f"model {model_id!r} is not in the curated catalog",
            )
        return entry

    def _definition(self, model_id: ModelId, operation: ImageOperation) -> ModelDefinition:
        definition = self._entry(model_id)[0]
        if operation not in definition.spec.operations:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"model {model_id} does not support {operation.value}",
            )
        return definition
