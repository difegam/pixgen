from pixgen.cli import invoke
from pixgen.cli.invoke import CommandInvoker
from pixgen.cli.options import ExecutionOptions
from pixgen.cli.outcome import ExitStatus, exit_status
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
    """Return a fixed result while retaining invocation arguments."""

    def __init__(self, result: CommandResult, events: list[str]) -> None:
        self._result = result
        self._events = events
        self.observer: object | None = None

    async def run(self, *_args, **kwargs) -> CommandResult:
        self.observer = kwargs.get("observer")
        self._events.append("run")
        return self._result


def _result() -> CommandResult:
    return CommandResult(
        run_id="019cb94c-af33-7e3a-80c1-03d0294010b8",
        results=(
            TargetResult(
                model="fake/model",
                variant=1,
                artifact_path="output.png",
                media_type="image/png",
            ),
        ),
    )


async def test_invoker_stops_progress_and_returns_outcome(monkeypatch) -> None:
    events: list[str] = []
    progress = RecordingProgress(events)
    result = _result()
    application = RecordingApplication(result, events)

    monkeypatch.setattr(
        invoke,
        "create_generation_progress",
        lambda *, as_json: None if as_json else progress,
    )

    outcome = await CommandInvoker(application).invoke(
        ImageCreateIntent(prompt="test"),
        SharedSelection(models=("fake/model",)),
        ExecutionOptions(),
    )

    assert outcome.result is result
    assert outcome.as_json is False
    assert outcome.relative_output_paths is True
    assert exit_status(outcome.result) is ExitStatus.SUCCESS
    assert application.observer is progress
    assert events == ["run", "stop"]


async def test_invoker_excludes_progress_from_json(monkeypatch) -> None:
    application = RecordingApplication(_result(), [])
    factory_calls: list[bool] = []

    def create_progress(*, as_json: bool) -> None:
        factory_calls.append(as_json)

    monkeypatch.setattr(invoke, "create_generation_progress", create_progress)

    outcome = await CommandInvoker(application).invoke(
        ImageCreateIntent(prompt="test"),
        SharedSelection(models=("fake/model",)),
        ExecutionOptions(json=True),
    )

    assert factory_calls == [True]
    assert application.observer is None
    assert outcome.as_json is True


async def test_invoker_keeps_explicit_output_paths_absolute(monkeypatch, tmp_path) -> None:
    application = RecordingApplication(_result(), [])
    monkeypatch.setattr(invoke, "create_generation_progress", lambda **_kwargs: None)

    outcome = await CommandInvoker(application).invoke(
        ImageCreateIntent(prompt="test"),
        SharedSelection(models=("fake/model",)),
        ExecutionOptions(output_dir=tmp_path / "custom-output"),
    )

    assert outcome.relative_output_paths is False
