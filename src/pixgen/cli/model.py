"""Model sub-app with list and get commands."""

from typing import TYPE_CHECKING

from cyclopts import App

from pixgen.cli.render import render_model_get_result, render_model_list_result
from pixgen.core.errors import ErrorCode
from pixgen.core.results import ModelGetResult, ModelListResult, PublicError

if TYPE_CHECKING:
    from pixgen.providers.registry import ProviderRegistry

__all__: list[str] = [
    "build_model_app",
]


def build_model_app(registry: ProviderRegistry) -> App:
    """Build the model sub-app."""
    app = App(name="model", help="Offline curated-model catalogue")

    @app.command(name="list", alias=["ls"])
    def list_models(*, json: bool = False) -> None:
        """List available models and supported operations."""
        models = registry.models()
        result = ModelListResult(models=models)
        render_model_list_result(result, as_json=json)

    @app.command(name="get")
    def get_model(
        model_id: str,
        *,
        json: bool = False,
    ) -> None:
        """Show one model's input and parameter schema."""

        try:
            spec = registry.get_model(model_id)
        except Exception as exc:
            result = ModelGetResult(
                error=PublicError(code=ErrorCode.MODEL_NOT_FOUND, message=str(exc))
            )
            render_model_get_result(result, as_json=json)
            raise SystemExit(2) from exc

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
        render_model_get_result(result, as_json=json)

    return app
