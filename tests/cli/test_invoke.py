import pytest

from pixgen.application import RunOutcome
from pixgen.cli import invoke
from pixgen.cli.invoke import CommandInvoker
from pixgen.cli.options import ExecutionOptions
from pixgen.core.requests import ImageCreateIntent, SharedSelection
from pixgen.core.results import CommandResult, TargetResult


class RecordingProgress:
    """Track progress lifecycle calls from the invoker."""

    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True
        self._events.append("stop")


class RecordingApplication:
    """Return a fixed outcome while retaining invocation arguments."""

    def __init__(self, outcome: RunOutcome, events: list[str]) -> None:
        self._outcome = outcome
        self._events = events
        self.observer: object | None = None

    async def run(self, *_args, **kwargs) -> RunOutcome:
        self.observer = kwargs.get("observer")
        self._events.append("run")
        return self._outcome


def _outcome(exit_code: int = 4) -> RunOutcome:
    return RunOutcome(
        result=CommandResult(
            run_id="019cb94c-af33-7e3a-80c1-03d0294010b8",
            results=(
                TargetResult(
                    model="fake/model",
                    variant=1,
                    artifact_path="output.png",
                    media_type="image/png",
                ),
            ),
        ),
        exit_code=exit_code,
    )


async def test_invoker_stops_progress_before_rendering(monkeypatch) -> None:
    events: list[str] = []
    progress = RecordingProgress(events)
    application = RecordingApplication(_outcome(), events)

    monkeypatch.setattr(
        invoke,
        "create_generation_progress",
        lambda *, as_json: None if as_json else progress,
    )

    def render_result(*_args, **_kwargs) -> None:
        assert progress.stopped
        events.append("render")

    monkeypatch.setattr(invoke, "render_command_result", render_result)

    with pytest.raises(SystemExit) as exc_info:
        await CommandInvoker(application).invoke(
            ImageCreateIntent(prompt="test"),
            SharedSelection(models=("fake/model",)),
            ExecutionOptions(),
        )

    assert exc_info.value.code == 4
    assert application.observer is progress
    assert events == ["run", "stop", "render"]


async def test_invoker_excludes_progress_from_json(monkeypatch) -> None:
    events: list[str] = []
    application = RecordingApplication(_outcome(exit_code=0), events)
    factory_calls: list[bool] = []
    render_json: list[bool] = []

    def create_progress(*, as_json: bool) -> None:
        factory_calls.append(as_json)

    monkeypatch.setattr(invoke, "create_generation_progress", create_progress)
    monkeypatch.setattr(
        invoke,
        "render_command_result",
        lambda _result, *, as_json: render_json.append(as_json),
    )

    with pytest.raises(SystemExit) as exc_info:
        await CommandInvoker(application).invoke(
            ImageCreateIntent(prompt="test"),
            SharedSelection(models=("fake/model",)),
            ExecutionOptions(json=True),
        )

    assert exc_info.value.code == 0
    assert factory_calls == [True]
    assert application.observer is None
    assert render_json == [True]
