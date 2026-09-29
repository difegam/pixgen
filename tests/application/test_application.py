"""Tests for application orchestration."""

import asyncio
from typing import TYPE_CHECKING

import pytest

from pixgen.application import ImageApplication
from pixgen.config.models import Defaults, GenerationSettings, Settings
from pixgen.core.errors import ErrorCode
from pixgen.core.parameters import ProviderParams, SharedImageParams
from pixgen.core.requests import ImageCreateIntent, NativeSelection, SharedSelection
from pixgen.providers.base import PreparedImageRequest, ProviderImage
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from pathlib import Path

    from pixgen.core.models import ModelSpec


class CapturedParams(ProviderParams):
    """Native parameters used to check they reach the provider unchanged."""

    quality: str | None = None


class SlowProvider:
    """Minimal provider for application timing tests."""

    name = "fake"

    def __init__(self, model: ModelSpec, delay: float) -> None:
        self._model = model
        self._delay = delay

    @property
    def available(self) -> bool:
        return True

    def models(self) -> tuple[ModelSpec, ...]:
        return (self._model,)

    def parameter_schema(self, _model: str, _operation: object) -> dict[str, object]:
        return {}

    def validate(
        self,
        *,
        intent: object,
        model: ModelSpec,
        parameters: object = None,  # noqa: ARG002
    ) -> object:
        from pixgen.core.requests import ValidatedImageRequest

        return ValidatedImageRequest(intent=intent, model=model, parameters=ProviderParams())

    def declared_media_type(self, _request: object) -> str:
        return "image/png"

    async def generate(self, _request: PreparedImageRequest) -> ProviderImage:
        await asyncio.sleep(self._delay)
        return ProviderImage(b"png", "image/png")


class CancellableProvider(SlowProvider):
    """Provider that records whether its request receives cancellation."""

    def __init__(self, model: ModelSpec) -> None:
        super().__init__(model, 0)
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def generate(self, _request: PreparedImageRequest) -> ProviderImage:
        self.started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return ProviderImage(b"png", "image/png")


class FatalProviderError(BaseException):
    """Fatal provider failure that must escape application error handling."""


class FatalProvider(SlowProvider):
    """Provider that fails after a sibling request starts."""

    def __init__(self, model: ModelSpec, sibling_started: asyncio.Event) -> None:
        super().__init__(model, 0)
        self._sibling_started = sibling_started

    async def generate(self, _request: PreparedImageRequest) -> ProviderImage:
        await self._sibling_started.wait()
        raise FatalProviderError


class RecordingObserver:
    """Record generation lifecycle events for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object, object | None]] = []

    def run_started(self, plans: object) -> None:
        self.events.append(("run_started", plans, None))

    def job_started(self, plan: object) -> None:
        self.events.append(("job_started", plan, None))

    def job_finished(self, plan: object, result: object) -> None:
        self.events.append(("job_finished", plan, result))


class TestImageApplication:
    """Test application-level result handling."""

    async def test_reports_each_serialised_job_lifecycle(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        registry = ProviderRegistry((SlowProvider(model, 0),))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(output_dir=tmp_path, max_parallel_requests=1),
        )
        observer = RecordingObserver()

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            variants=2,
            observer=observer,
        )

        assert [event[0] for event in observer.events] == [
            "run_started",
            "job_started",
            "job_finished",
            "job_started",
            "job_finished",
        ]
        planned = observer.events[0][1]
        assert tuple(plan.variant for plan in planned) == (1, 2)
        assert [event[1].variant for event in observer.events[1:]] == [1, 1, 2, 2]
        assert [event[2] for event in observer.events if event[0] == "job_finished"] == list(
            outcome.result.results
        )

    async def test_reports_synthetic_run_timeout_result(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        registry = ProviderRegistry((SlowProvider(model, 0.6),))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(
                output_dir=tmp_path,
                max_parallel_requests=1,
                max_jobs=2,
                run_timeout_seconds=1,
            ),
        )
        observer = RecordingObserver()

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            variants=2,
            observer=observer,
        )

        timed_out = observer.events[-1]
        assert timed_out[0] == "job_finished"
        assert timed_out[1].variant == 2
        assert timed_out[2] == outcome.result.results[1]
        assert timed_out[2].error is not None
        assert timed_out[2].error.message == "run deadline exceeded"

    async def test_does_not_report_preflight_failure(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        registry = ProviderRegistry((UnavailableProvider(model),))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(output_dir=tmp_path),
        )
        observer = RecordingObserver()

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            observer=observer,
        )

        assert outcome.exit_code == 2
        assert observer.events == []

    @pytest.mark.asyncio
    async def test_preserves_preflight_error_code(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        registry = ProviderRegistry((UnavailableProvider(model),))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(output_dir=tmp_path),
        )
        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
        )

        assert outcome.result.error is not None
        assert outcome.result.error.code == ErrorCode.CREDENTIAL_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_rejects_incompatible_shared_ratio_before_generation(
        self, tmp_path: Path
    ) -> None:
        calls = 0

        def make_client() -> object:
            nonlocal calls
            calls += 1
            raise AssertionError("client must not be created during strict preflight")

        provider = OpenAIProvider(None, client_factory=make_client)
        registry = ProviderRegistry((provider,))
        settings = Settings(
            defaults=Defaults(image_create_models=("openai/gpt-image-2",)),
            generation=GenerationSettings(output_dir=tmp_path),
        )
        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            selection=SharedSelection(
                models=("openai/gpt-image-2", "openai/gpt-image-1-mini"),
                parameters=SharedImageParams(aspect_ratio="16:9"),
            ),
        )

        assert outcome.exit_code == 2
        assert outcome.result.error is not None
        assert "gpt-image-1-mini" in outcome.result.error.message
        assert calls == 0
        assert await asyncio.to_thread(lambda: tuple(tmp_path.iterdir())) == ()

    @pytest.mark.asyncio
    async def test_rejects_duplicate_models_before_submission(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        provider = SlowProvider(model, 0)
        registry = ProviderRegistry((provider,))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(output_dir=tmp_path),
        )

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            selection=SharedSelection(models=("fake/model", "fake/model")),
        )

        assert outcome.exit_code == 2
        assert outcome.result.error is not None
        assert outcome.result.error.code == ErrorCode.INVALID_REQUEST

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("selection", "expected"),
        [
            pytest.param(
                NativeSelection(model="fake/model", parameters=CapturedParams(quality="high")),
                CapturedParams(quality="high"),
                id="native",
            ),
            pytest.param(
                SharedSelection(parameters=SharedImageParams(aspect_ratio="16:9")),
                SharedImageParams(aspect_ratio="16:9"),
                id="shared",
            ),
            pytest.param(None, SharedImageParams(), id="none"),
        ],
    )
    async def test_passes_selection_parameters_to_provider(
        self, tmp_path: Path, selection, expected
    ) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        provider = ParameterCapturingProvider(model)
        registry = ProviderRegistry((provider,))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(output_dir=tmp_path),
        )

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            selection=selection,
        )

        assert outcome.exit_code == 0
        assert provider.parameters == expected

    @pytest.mark.asyncio
    async def test_rejects_nonpositive_timeout_before_submission(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        provider = SlowProvider(model, 0)
        registry = ProviderRegistry((provider,))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(output_dir=tmp_path),
        )

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            timeout_seconds=0,
        )

        assert outcome.exit_code == 2
        assert outcome.result.error is not None
        assert outcome.result.error.code == ErrorCode.INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_run_timeout_is_shared_by_all_jobs(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        registry = ProviderRegistry((SlowProvider(model, 0.6),))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(
                output_dir=tmp_path,
                max_parallel_requests=1,
                max_jobs=2,
                run_timeout_seconds=1,
            ),
        )

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
            variants=2,
        )

        assert outcome.result.results[0].artifact_path is not None
        assert outcome.result.results[1].error is not None
        assert outcome.result.results[1].error.code == ErrorCode.TIMEOUT

    @pytest.mark.asyncio
    async def test_request_timeout_cancels_provider_job(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        provider = CancellableProvider(model)
        registry = ProviderRegistry((provider,))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(
                output_dir=tmp_path,
                request_timeout_seconds=1,
            ),
        )

        outcome = await ImageApplication(registry, settings).run(
            ImageCreateIntent(prompt="test"),
        )

        assert outcome.result.results[0].error is not None
        assert outcome.result.results[0].error.code == ErrorCode.TIMEOUT
        assert provider.cancelled.is_set()

    @pytest.mark.asyncio
    async def test_cancelling_run_cancels_provider_jobs(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        model = make_model_spec(model_id="fake/model")
        provider = CancellableProvider(model)
        registry = ProviderRegistry((provider,))
        settings = Settings(
            defaults=Defaults(image_create_models=("fake/model",)),
            generation=GenerationSettings(output_dir=tmp_path, run_timeout_seconds=60),
        )
        run_task = asyncio.create_task(
            ImageApplication(registry, settings).run(ImageCreateIntent(prompt="test"))
        )

        await provider.started.wait()
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

        await asyncio.wait_for(provider.cancelled.wait(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_fatal_job_failure_cancels_sibling_jobs(self, tmp_path: Path) -> None:
        from tests.factories import make_model_spec

        fatal_model = make_model_spec(model_id="fatal/fatal")
        slow_model = make_model_spec(model_id="slow/slow")
        slow_provider = CancellableProvider(slow_model)
        fatal_provider = FatalProvider(fatal_model, slow_provider.started)
        fatal_provider.name = "fatal"
        slow_provider.name = "slow"
        registry = ProviderRegistry((fatal_provider, slow_provider))
        settings = Settings(
            defaults=Defaults(image_create_models=("fatal/fatal", "slow/slow")),
            generation=GenerationSettings(output_dir=tmp_path, max_parallel_requests=2),
        )

        with pytest.raises(BaseExceptionGroup) as exc_info:
            await ImageApplication(registry, settings).run(ImageCreateIntent(prompt="test"))

        assert exc_info.value.subgroup(FatalProviderError) is not None
        await asyncio.wait_for(slow_provider.cancelled.wait(), timeout=0.5)


class UnavailableProvider(SlowProvider):
    """Provider used to exercise credential preflight failures."""

    def __init__(self, model: ModelSpec) -> None:
        super().__init__(model, 0)

    @property
    def available(self) -> bool:
        return False


class ParameterCapturingProvider(SlowProvider):
    """Provider that records the parameters the application asks it to validate."""

    def __init__(self, model: ModelSpec) -> None:
        super().__init__(model, 0)
        self.parameters: object = None

    def validate(self, *, intent: object, model: ModelSpec, parameters: object = None) -> object:
        self.parameters = parameters
        return super().validate(intent=intent, model=model, parameters=parameters)
