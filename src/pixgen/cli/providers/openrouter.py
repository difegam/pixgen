"""Build OpenRouter native Cyclopts image commands."""

from typing import Literal

from pydantic import Field

from pixgen.cli.providers.native import NativeProviderSpec
from pixgen.core.parameters import ProviderParams
from pixgen.providers.openrouter import OPENROUTER_CATALOGUE

__all__: list[str] = ["OPENROUTER_SPEC", "OpenRouterCliParams"]

OpenRouterCliAspectRatio = Literal[
    "auto",
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:1",
    "4:3",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
]


class OpenRouterCliParams(ProviderParams):
    """Collect model-native flags before resolving them against the selected model."""

    aspect_ratio: OpenRouterCliAspectRatio | None = Field(default=None)
    resolution: Literal["512", "1K", "2K", "4K"] | None = Field(default=None)
    quality: Literal["auto", "low", "medium", "high", "xhigh", "max"] | None = Field(default=None)
    background: Literal["auto", "transparent", "opaque"] | None = Field(default=None)
    output_compression: int | None = Field(default=None, ge=0, le=100)


def _resolve_params(model_id: str, params: ProviderParams) -> ProviderParams:
    """Validate the collected flags against the selected catalogue model's parameters."""
    definition = next(
        (item for item in OPENROUTER_CATALOGUE if item.spec.id == model_id),
        None,
    )
    parameter_type = definition.parameter_type if definition is not None else OpenRouterCliParams
    return parameter_type.model_validate(params.model_dump(exclude_none=True))


OPENROUTER_SPEC = NativeProviderSpec(
    name="openrouter",
    display_name="OpenRouter",
    params_type=OpenRouterCliParams,
    model_error="OpenRouter native commands require an OpenRouter model name",
    allow_nested_model=True,
    resolve_params=_resolve_params,
)
