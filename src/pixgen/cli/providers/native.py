"""Build provider-native Cyclopts image commands from a provider spec."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated, Any

from cyclopts import App, Parameter

from pixgen.cli.options import ExecutionOptions
from pixgen.cli.outcome import CliOutcome, cli_command
from pixgen.core.models import ImageOperation
from pixgen.core.parameters import ProviderParams  # noqa: TC001  (read when annotations are set)
from pixgen.core.requests import ImageCreateIntent, ImageEditIntent, NativeSelection
from pixgen.providers.shared import normalize_model_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from pixgen.cli.invoke import CommandInvoker

__all__: list[str] = ["NativeCliFactory", "NativeProviderSpec", "build_native_app"]


@dataclass(frozen=True, slots=True)
class NativeProviderSpec:
    """Describe one provider's native command surface.

    Attributes:
        name: Provider sub-command name, also the model prefix.
        display_name: Provider name used in help and docstrings.
        params_type: Flattened native parameter model exposed as CLI flags.
        model_error: Message raised when the model name is not for this provider.
        select: Builds the selection from the model name and parsed parameters.
            Defaults to normalising the model name and wrapping the parameters.
    """

    name: str
    display_name: str
    params_type: type[ProviderParams]
    model_error: str
    select: Callable[[str, ProviderParams], NativeSelection] | None = None


def _default_select(
    spec: NativeProviderSpec, model: str, params: ProviderParams
) -> NativeSelection:
    model_id = normalize_model_id(model, prefix=spec.name, error_message=spec.model_error)
    return NativeSelection(model=model_id, parameters=params)


def _register(app: App, command: Callable[..., Any], params_annotation: Any) -> None:
    """Register a command whose ``params`` type is only known at runtime.

    The annotation goes on the wrapped command because on 3.14 ``functools.wraps``
    copies lazy annotations, so setting it before wrapping would be lost.
    """
    wrapped = cli_command()(command)
    wrapped.__annotations__["params"] = params_annotation
    app.default(wrapped)


def build_native_app(
    spec: NativeProviderSpec,
    operation: ImageOperation,
    invoker: CommandInvoker,
) -> App:
    """Build one provider-native sub-app for an operation."""
    app = App(name=spec.name, help=f"{spec.display_name} image generation options")
    select = spec.select or partial(_default_select, spec)
    default_params = spec.params_type()
    params_annotation = Annotated[spec.params_type, Parameter(name="*")]

    async def run(
        intent: ImageCreateIntent | ImageEditIntent,
        model: str,
        params: ProviderParams,
        **options: Any,
    ) -> CliOutcome:
        return await invoker.invoke(intent, select(model, params), ExecutionOptions(**options))

    if operation is ImageOperation.IMAGE_CREATE:

        async def create(
            prompt: str,
            *,
            model: str,
            params: ProviderParams = default_params,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> CliOutcome:
            return await run(
                ImageCreateIntent(prompt=prompt),
                model,
                params,
                variants=variants,
                output=output,
                output_dir=output_dir,
                mkdir=mkdir,
                force=force,
                timeout_seconds=timeout_seconds,
                json=json,
            )

        create.__doc__ = f"Create an image with {spec.display_name} native parameters."
        _register(app, create, params_annotation)

    else:

        async def edit(
            prompt: str,
            *,
            image: list[Path],
            model: str,
            params: ProviderParams = default_params,
            variants: int = 1,
            output: Path | None = None,
            output_dir: Path | None = None,
            mkdir: bool = False,
            force: bool = False,
            timeout_seconds: int | None = None,
            json: bool = False,
        ) -> CliOutcome:
            return await run(
                ImageEditIntent(prompt=prompt, images=tuple(image)),
                model,
                params,
                variants=variants,
                output=output,
                output_dir=output_dir,
                mkdir=mkdir,
                force=force,
                timeout_seconds=timeout_seconds,
                json=json,
            )

        edit.__doc__ = f"Edit images with {spec.display_name} native parameters."
        _register(app, edit, params_annotation)

    return app


class NativeCliFactory:
    """Build one provider's native commands from its spec."""

    operations = frozenset({ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT})

    def __init__(self, spec: NativeProviderSpec) -> None:
        """Initialise the factory for one provider spec."""
        self.spec = spec
        self.name = spec.name

    def build(self, operation: ImageOperation, invoker: CommandInvoker) -> App:
        """Return the provider app for one operation."""
        return build_native_app(self.spec, operation, invoker)
