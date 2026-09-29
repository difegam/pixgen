"""Model sub-app with list and get commands."""

from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.outcome import CliOutcome, cli_command
from pixgen.core.results import ModelGetResult, ModelListResult, PublicError

if TYPE_CHECKING:
    from pixgen.providers.registry import ProviderRegistry

__all__: list[str] = [
    "build_model_app",
]


def _model_get_error(error: PublicError) -> ModelGetResult:
    """Wrap a lookup failure in a model get result."""
    return ModelGetResult(error=error)


def build_model_app(registry: ProviderRegistry) -> App:
    """Build the model sub-app."""
    app = App(name="model", help="Offline curated-model catalogue")

    @app.command(name="list", alias=["ls"])
    def list_models(*, json: bool = False) -> CliOutcome:
        """List available models and supported operations."""
        return CliOutcome(ModelListResult(models=registry.models()), as_json=json)

    @app.command(name="get")
    @cli_command(_model_get_error)
    def get_model(
        model_id: str,
        *,
        json: bool = False,
    ) -> CliOutcome:
        """Show one model's input and parameter schema."""
        spec = registry.get_model(model_id)
        provider = registry.provider_for(spec.id)
        schemas = {}
        shared_aspect_ratios = {}
        for op in spec.operations:
            schemas[op.value] = provider.parameter_schema(spec.id, op)
            ratios = registry.shared_aspect_ratios(spec.id, op)
            if ratios:
                shared_aspect_ratios[op.value] = ratios

        result = ModelGetResult(
            model=spec,
            parameter_schemas=schemas,
            shared_aspect_ratios=shared_aspect_ratios,
        )
        return CliOutcome(result, as_json=json)

    return app
