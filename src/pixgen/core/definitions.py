"""Define curated models together with their native parameters."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pixgen.core.aspect_ratio import normalise_aspect_ratio
from pixgen.core.errors import ErrorCode, PixgenError, validation_message
from pixgen.core.models import JsonObject, ModelSpec
from pixgen.core.parameters import ProviderParams, SharedImageParams

__all__: list[str] = ["ModelDefinition"]


class ModelDefinition[P: ProviderParams](BaseModel):
    """Define one curated model: its spec, native parameters, and shared ratios."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
    )

    spec: ModelSpec
    parameter_type: type[P] = Field(exclude=True)
    defaults: P
    aspect_ratios: Mapping[str, JsonObject] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _copy_mappings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            copied = dict(data)
            copied["aspect_ratios"] = deepcopy(data.get("aspect_ratios", {}))
            return copied
        return data

    @model_validator(mode="after")
    def _validate_definition(self) -> ModelDefinition[P]:
        canonical: dict[str, JsonObject] = {}
        for raw_ratio, override in self.aspect_ratios.items():
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

    def resolve_parameters(self, parameters: SharedImageParams | ProviderParams | None) -> P:
        """Resolve shared or native parameters into this model's native parameters.

        Raises:
            PixgenError: If a shared ratio is unsupported or native values fall outside
                this model's parameter type.
        """
        if parameters is None:
            parameters = SharedImageParams()
        if isinstance(parameters, SharedImageParams):
            try:
                return self.resolve(parameters)
            except ValueError as exc:
                supported = ", ".join(sorted(self.aspect_ratios))
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    f"model {self.spec.id} does not support aspect ratio "
                    f"{parameters.aspect_ratio}; supported ratios: {supported}",
                ) from exc
        try:
            return self.parameter_type.model_validate(parameters.model_dump())
        except ValidationError as exc:
            raise PixgenError(ErrorCode.INVALID_REQUEST, validation_message(exc)) from exc
