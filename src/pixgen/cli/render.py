"""Render command results for human and JSON output."""

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from pixgen.cli.progress import GenerationProgress

if TYPE_CHECKING:
    from pixgen.core.results import CommandResult, ModelGetResult, ModelListResult

__all__: list[str] = [
    "create_generation_progress",
    "render_command_result",
    "render_model_get_result",
    "render_model_list_result",
]

_stdout_console = Console(highlight=False, markup=False)
_stderr_console = Console(stderr=True, highlight=False, markup=False)


def render_command_result(
    result: CommandResult,
    *,
    as_json: bool,
    relative_output_paths: bool = False,
) -> None:
    """Render a CommandResult to stdout."""
    if as_json:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    if result.error:
        _stderr_console.print(f"Error: {result.error.message}")
        return

    if _stdout_console.is_interactive:
        _render_interactive_command_result(result, relative_output_paths=relative_output_paths)
        return

    _stdout_console.print(f"Run ID: {result.run_id}")
    for target in result.results:
        if target.artifact_path:
            _stdout_console.print(f"  {target.model} v{target.variant}: {target.artifact_path}")
            for warning in target.warnings:
                _stderr_console.print(f"  Warning: {warning}")
        elif target.error:
            _stderr_console.print(f"  {target.model} v{target.variant}: {target.error.message}")


def create_generation_progress(*, as_json: bool) -> GenerationProgress | None:
    """Create a live progress renderer for interactive human output."""
    if (
        as_json
        or not _stdout_console.is_interactive
        or not _stderr_console.is_interactive
        or _stdout_console.is_dumb_terminal
        or _stderr_console.is_dumb_terminal
    ):
        return None
    return GenerationProgress(_stderr_console)


def _render_interactive_command_result(
    result: CommandResult, *, relative_output_paths: bool
) -> None:
    _stdout_console.print(f"Run ID: {result.run_id}")
    table = Table(
        "Model",
        "Variant",
        "Status",
        "Output",
        box=box.SIMPLE,
        header_style="bold",
        highlight=False,
    )
    for target in result.results:
        if target.error is not None:
            status = Text("Failed", style="red")
            detail = Text(target.error.message)
        else:
            artifact_path = target.artifact_path
            if artifact_path is None:
                raise RuntimeError("successful target is missing its artifact path")
            output_path = _display_output_path(
                artifact_path,
                relative_output_paths=relative_output_paths,
            )
            if target.warnings:
                status = Text("Saved with warnings", style="yellow")
                detail = Text("\n".join((output_path, *target.warnings)))
            else:
                status = Text("Saved", style="green")
                detail = Text(output_path)
        table.add_row(target.model, str(target.variant), status, detail)
    _stdout_console.print(table)


def _display_output_path(path: Path, *, relative_output_paths: bool) -> str:
    if not relative_output_paths:
        return str(path)
    return os.path.relpath(path, Path.cwd())


def render_model_list_result(result: ModelListResult, *, as_json: bool) -> None:
    """Render a ModelListResult to stdout."""
    if as_json:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    if result.error:
        _stderr_console.print(f"Error: {result.error.message}")
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
        _stderr_console.print(f"Error: {result.error.message}")
        return

    model = result.model
    if model is None:
        return
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

    if result.shared_aspect_ratios:
        _stdout_console.print("\nShared aspect ratios:")
        for op, ratios in result.shared_aspect_ratios.items():
            _stdout_console.print(f"  {op}: {', '.join(ratios)}")
