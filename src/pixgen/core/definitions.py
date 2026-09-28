"""Compose provider, model, and operation capability definitions."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixgen.core.models import (
    ImageOperation,
    JsonObject,
    MediaRole,
    MediaRoleSpec,
    ModelSpec,
)
from pixgen.core.parameters import ProviderParams, SharedImageParams

__all__: list[str] = ["ModelDefinition", "OperationDefinition", "ProviderDefinition"]


class OperationDefinition[P: ProviderParams](BaseModel):
    """Define native parameters and shared conversions for one operation."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
    )

    parameter_type: type[P] = Field(exclude=True)
    defaults: P
    media: Mapping[MediaRole, MediaRoleSpec]
    aspect_ratios: Mapping[str, JsonObject] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _copy_mappings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            copied = dict(data)
            copied["media"] = deepcopy(data.get("media", {}))
            copied["aspect_ratios"] = deepcopy(data.get("aspect_ratios", {}))
            return copied
        return data

    @model_validator(mode="after")
    def _validate_definition(self) -> OperationDefinition[P]:
        canonical: dict[str, JsonObject] = {}
        for raw_ratio, override in self.aspect_ratios.items():
            from pixgen.core.aspect_ratio import normalise_aspect_ratio

            ratio = normalise_aspect_ratio(raw_ratio)
            if ratio in canonical:
                raise ValueError(f"canonical aspect ratio collision: {ratio}")
            canonical[ratio] = deepcopy(dict(override))
            self.parameter_type.model_validate({**self.defaults.model_dump(), **override})
        object.__setattr__(self, "aspect_ratios", canonical)
        return self

    def resolve(self, shared: SharedImageParams) -> P:
        """Apply a shared request to defaults and validate native parameters."""
        override: JsonObject = {}
        if shared.aspect_ratio is not None:
            mapped_override = self.aspect_ratios.get(shared.aspect_ratio)
            if mapped_override is None:
                raise ValueError(f"unsupported aspect ratio: {shared.aspect_ratio}")
            override = mapped_override
        return self.parameter_type.model_validate({**self.defaults.model_dump(), **override})


class ModelDefinition[P: ProviderParams](BaseModel):
    """Compose a model catalogue entry with operation definitions."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    spec: ModelSpec
    operations: Mapping[ImageOperation, OperationDefinition[P]]

    @model_validator(mode="after")
    def _validate_operations(self) -> ModelDefinition[P]:
        if set(self.operations) != set(self.spec.operations):
            raise ValueError("model operations do not match model specification")
        return self


class ProviderDefinition[M: ModelDefinition[ProviderParams]](BaseModel):
    """Compose one provider's model catalogue."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    models: tuple[M, ...]

    @model_validator(mode="after")
    def _validate_models(self) -> ProviderDefinition[M]:
        ids = [model.spec.id for model in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate model ID in provider catalogue")
        for model_id in ids:
            if model_id.split("/", 1)[0] != self.name:
                raise ValueError("model ID does not match provider prefix")
        return self
