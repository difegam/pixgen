from io import StringIO
from pathlib import Path

from rich.console import Console

from pixgen.artifacts import OutputPlan
from pixgen.cli.progress import GenerationProgress
from pixgen.core.errors import ErrorCode
from pixgen.core.results import PublicError, TargetResult


def test_generation_progress_renders_target_statuses() -> None:
    console = Console(
        file=StringIO(),
        force_terminal=True,
        force_interactive=True,
        highlight=False,
        markup=False,
        record=True,
        width=120,
    )
    first = OutputPlan(model_id="fake/first", variant=1, path=Path("first.png"))
    second = OutputPlan(model_id="fake/second", variant=1, path=Path("second.png"))
    progress = GenerationProgress(console)

    progress.run_started((first, second))
    progress.job_started(first)
    progress.job_finished(
        first,
        TargetResult(
            model="fake/first",
            variant=1,
            artifact_path=Path("first.png"),
            media_type="image/png",
        ),
    )
    progress.job_finished(
        second,
        TargetResult(
            model="fake/second",
            variant=1,
            error=PublicError(code=ErrorCode.PROVIDER_FAILURE, message="provider failed"),
        ),
    )
    progress.stop()

    output = console.export_text()
    assert "1/2" in output
    assert "2/2" in output
    assert "fake/first v1" in output
    assert "fake/second v1" in output
    assert "Saved" in output
    assert "Failed" in output
    assert "provider failed" in output


def test_generation_progress_stop_is_safe_before_run_started() -> None:
    progress = GenerationProgress(Console(file=StringIO(), force_terminal=True))

    progress.stop()
