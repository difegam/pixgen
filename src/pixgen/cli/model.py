"""Model sub-app with list and get commands."""

from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Group, Parameter, validators

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
    app = App(
        name="model",
        help="Show supported models and their details.",
        group="Model Details",
    )

    output_format = Group(
        validator=validators.MutuallyExclusive(),
        default_parameter=Parameter(show_default=False, negative=""),
        help="Output format of the command result.",
    )

    @app.command(name="list", alias=["ls"])
    def list_models(
        *,
        json: Annotated[bool, Parameter(group=(app.group_parameters, output_format))] = False,
        tree: Annotated[bool, Parameter(group=(app.group_parameters, output_format))] = False,
    ) -> CliOutcome:
        """List available models and supported operations.

        Args:
            json: Emit the machine-readable JSON result.
            tree: Group models by provider in a tree.
        """
        return CliOutcome(ModelListResult(models=registry.models()), as_json=json, as_tree=tree)

    @app.command(name="get")
    @cli_command(_model_get_error)
    def get_model(
        model_id: str,
        *,
        json: bool = False,
    ) -> CliOutcome:
        """Show one model's input and parameter schema."""
        spec = registry.get_model(model_id)
        schemas = {}
        shared_aspect_ratios = {}
        for op in spec.operations:
            schemas[op.value] = registry.parameter_schema(spec.id, op)
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
