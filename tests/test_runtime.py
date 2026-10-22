"""Tests for runtime composition and lazy clients."""

from unittest.mock import patch

import pytest
from PIL import Image
from pydantic import SecretStr

from pixgen.config.models import GenerationSettings, Settings
from pixgen.optimization.application import OptimizeApplication
from pixgen.optimization.models import OptimizeRequest
from pixgen.runtime import build_runtime, get_gemini_factory


def test_build_runtime_does_not_construct_clients_for_catalogue_commands() -> None:
    settings = Settings.model_construct(
        openai_api_key=SecretStr("openai-test"),
        gemini_api_key=SecretStr("gemini-test"),
        openrouter_api_key=SecretStr("openrouter-test"),
    )

    with (
        patch("pixgen.runtime.load_settings", return_value=settings),
        patch("pixgen.providers.http.httpx2.AsyncClient", autospec=True) as async_client,
    ):
        runtime = build_runtime()

    assert async_client.call_count == 0
    assert all(
        runtime.registry.provider_for(model.id).available for model in runtime.registry.models()
    )
    assert tuple(provider.name for provider in runtime.registry.providers()) == (
        "openai",
        "gemini",
        "openrouter",
    )
    openrouter = runtime.registry.provider_for("openrouter/google/gemini-3.1-flash-image")
    assert openrouter.available is True


def test_build_runtime_keeps_openrouter_catalogue_available_without_credentials() -> None:
    settings = Settings.model_construct(
        openai_api_key=None,
        gemini_api_key=None,
        openrouter_api_key=None,
    )

    with patch("pixgen.runtime.load_settings", return_value=settings):
        runtime = build_runtime()

    assert "openrouter/google/gemini-3.1-flash-image" in {
        model.id for model in runtime.registry.models()
    }
    assert (
        runtime.registry.provider_for("openrouter/google/gemini-3.1-flash-image").available is False
    )


@pytest.mark.parametrize(
    ("request_retries", "expected_attempts"),
    [(0, 1), (2, 3)],
    ids=["disabled", "configured"],
)
def test_gemini_factory_maps_retry_count_to_total_attempts(
    request_retries: int, expected_attempts: int
) -> None:
    with patch("google.genai.Client", autospec=True) as client:
        factory = get_gemini_factory(
            SecretStr("gemini-test"),
            request_timeout_seconds=30,
            request_retries=request_retries,
        )
        assert factory is not None
        factory()

    options = client.call_args.kwargs["http_options"]
    assert options.retry_options.attempts == expected_attempts


def test_build_runtime_passes_retry_setting_to_provider_factories() -> None:
    settings = Settings.model_construct(
        generation=GenerationSettings(request_retries=2),
        openai_api_key=SecretStr("openai-test"),
        gemini_api_key=SecretStr("gemini-test"),
        openrouter_api_key=SecretStr("openrouter-test"),
    )

    with (
        patch("pixgen.runtime.load_settings", return_value=settings),
        patch("pixgen.runtime.make_http_client_factory") as http_factory,
        patch("pixgen.runtime.get_gemini_factory") as gemini_factory,
    ):
        build_runtime()

    assert [call.kwargs["request_retries"] for call in http_factory.call_args_list] == [2, 2]
    assert gemini_factory.call_args.args[2] == 2


def test_build_runtime_composes_group_repository_for_resolved_config_path(
    monkeypatch, tmp_path
) -> None:
    config_path = tmp_path / "pixgen.toml"
    monkeypatch.setenv("PIXGEN_CONFIG", str(config_path))
    settings = Settings.model_construct()

    with patch("pixgen.runtime.load_settings", return_value=settings):
        runtime = build_runtime()

    assert runtime.group_repository.path == config_path


class TestOptimizeRuntime:
    @pytest.mark.parametrize("dry_run", [True, False], ids=["plan", "execute"])
    def test_composes_local_application_without_provider_clients(self, tmp_path, dry_run) -> None:
        source = tmp_path / "source.png"
        with Image.new("RGB", (40, 20), "red") as image:
            image.save(source)
        settings = Settings.model_construct(
            openai_api_key=SecretStr("openai-test"), gemini_api_key=SecretStr("gemini-test")
        )
        with (
            patch("pixgen.runtime.load_settings", return_value=settings),
            patch(
                "pixgen.providers.http.httpx2.AsyncClient.__init__", autospec=True
            ) as http_client,
            patch("google.genai.Client.__init__", autospec=True) as gemini_client,
        ):
            runtime = build_runtime()
            assert isinstance(runtime.optimize_application, OptimizeApplication)
            result = runtime.optimize_application.run(
                OptimizeRequest(
                    source=source, width=(20,), output=tmp_path / "output.png", dry_run=dry_run
                )
            )

        assert result.error is None
        assert result.dry_run is dry_run
        assert result.variants[0].output_path.exists() is not dry_run
        http_client.assert_not_called()
        gemini_client.assert_not_called()
