"""Render live, per-target image-generation feedback."""

from typing import TYPE_CHECKING

from rich.progress import (
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console, RenderableType

    from pixgen.artifacts import OutputPlan
    from pixgen.core.results import TargetResult

__all__: list[str] = ["GenerationProgress"]


class _StatusColumn(ProgressColumn):
    """Render a target status with its supplied style."""

    def render(self, task: Task) -> RenderableType:
        return Text(str(task.fields["status"]), style=str(task.fields["status_style"]))


class _GenerationSpinnerColumn(SpinnerColumn):
    """Render a static marker until a target starts generating."""

    def render(self, task: Task) -> RenderableType:
        if not task.started:
            return Text("·", style="dim")
        return super().render(task)


class GenerationProgress:
    """Render lifecycle events as a transient Rich progress display."""

    def __init__(self, console: Console, *, transient: bool = True) -> None:
        self._progress = Progress(
            _GenerationSpinnerColumn(finished_text="✓"),
            TextColumn("{task.fields[ordinal]}", markup=False),
            TextColumn("{task.description}", markup=False),
            _StatusColumn(),
            TextColumn(
                "{task.fields[detail]}",
                markup=False,
                table_column=Column(overflow="ellipsis"),
            ),
            TimeElapsedColumn(),
            console=console,
            redirect_stderr=False,
            redirect_stdout=False,
            transient=transient,
        )
        self._task_ids: dict[tuple[str, int], TaskID] = {}
        self._started = False

    def run_started(self, plans: tuple[OutputPlan, ...]) -> None:
        """Start displaying planned generation targets."""
        self._progress.start()
        self._started = True
        total = len(plans)
        for index, plan in enumerate(plans, start=1):
            self._task_ids[_target_key(plan)] = self._progress.add_task(
                f"{plan.model_id} v{plan.variant}",
                total=None,
                start=False,
                ordinal=f"{index}/{total}",
                status="Queued",
                status_style="dim",
                detail="",
            )

    def job_started(self, plan: OutputPlan) -> None:
        """Show a target currently generating."""
        task_id = self._task_ids[_target_key(plan)]
        self._progress.start_task(task_id)
        self._progress.update(
            task_id,
            status="Generating",
            status_style="cyan",
        )

    def job_finished(self, plan: OutputPlan, result: TargetResult) -> None:
        """Show a target's terminal result."""
        status, status_style, detail = _result_details(result)
        self._progress.update(
            self._task_ids[_target_key(plan)],
            completed=1,
            total=1,
            status=status,
            status_style=status_style,
            detail=detail,
        )

    def stop(self) -> None:
        """Stop the display if generation started."""
        if self._started:
            self._progress.stop()
            self._started = False


def _target_key(plan: OutputPlan) -> tuple[str, int]:
    return plan.model_id, plan.variant


def _result_details(result: TargetResult) -> tuple[str, str, str]:
    """Return the status, status style, and detail string for a target result."""

    if result.error is not None:
        return "Failed", "red", result.error.message
    if result.warnings:
        return (
            "Saved with warnings",
            "yellow",
            "\n".join((str(result.artifact_path), *result.warnings)),
        )
    return "Saved", "green", str(result.artifact_path)
