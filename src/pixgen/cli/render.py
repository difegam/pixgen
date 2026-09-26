"""Render command results for human and JSON output."""

import json
import sys
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from pixgen.core.results import CommandResult, ModelGetResult, ModelListResult

__all__: list[str] = [
    "render_command_result",
    "render_model_get_result",
    "render_model_list_result",
]

_stdout_console = Console(highlight=False)
_stderr_console = Console(stderr=True, highlight=False)


def render_command_result(result: CommandResult, *, as_json: bool) -> None:
    """Render a CommandResult to stdout."""
    if as_json:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    if result.error:
        _stderr_console.print(f"[red]Error:[/red] {result.error.message}")
        return

    _stdout_console.print(f"Run ID: {result.run_id}")
    for target in result.results:
        if target.artifact_path:
            _stdout_console.print(f"  {target.model} v{target.variant}: {target.artifact_path}")
            for warning in target.warnings:
                _stderr_console.print(f"  [yellow]Warning:[/yellow] {warning}")
        elif target.error:
            _stderr_console.print(
                f"  [red]{target.model} v{target.variant}:[/red] {target.error.message}"
            )


def render_model_list_result(result: ModelListResult, *, as_json: bool) -> None:
    """Render a ModelListResult to stdout."""
    if as_json:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    if result.error:
        _stderr_console.print(f"[red]Error:[/red] {result.error.message}")
        return

    for model in result.models:
        ops = ", ".join(sorted(model.operations))
        _stdout_console.print(f"{model.id} — {model.display_name} [{ops}]")


def render_model_get_result(result: ModelGetResult, *, as_json: bool) -> None:
    """Render a ModelGetResult to stdout."""
    if as_json:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    if result.error:
        _stderr_console.print(f"[red]Error:[/red] {result.error.message}")
        return

    model = result.model
    assert model is not None  # noqa: S101
    _stdout_console.print(f"ID: {model.id}")
    _stdout_console.print(f"Name: {model.display_name}")
    _stdout_console.print(f"Operations: {', '.join(sorted(model.operations))}")
    _stdout_console.print(f"Documentation: {model.documentation_url}")
    _stdout_console.print(f"Verified: {model.verified_at}")

    if result.parameter_schemas:
        _stdout_console.print("\nParameter schemas:")
        for op, schema in result.parameter_schemas.items():
            _stdout_console.print(f"  {op}:")
            _stdout_console.print(json.dumps(schema, indent=4))
