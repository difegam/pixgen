"""Tests for the root Pixgen command tree."""

import contextlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from cyclopts import App
from cyclopts.exceptions import UnknownCommandError, UnknownOptionError
from PIL import Image
from pydantic import SecretStr

from pixgen.application import ImageApplication
from pixgen.cli.app import build_app
from pixgen.cli.model import build_model_app
from pixgen.cli.providers.gemini import GeminiCliFactory
from pixgen.cli.providers.openai import OpenAICliFactory
from pixgen.config.models import Settings
from pixgen.config.writer import ConfigRepository
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.models import ImageOperation, ModelSpec
from pixgen.optimization.application import OptimizeApplication
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.registry import ProviderRegistry
from tests.factories import make_model_definition, make_model_spec


class UnregisteredFactory:
    """Factory whose provider is absent from the registry."""

    name = "example"
    operations = frozenset({ImageOperation.IMAGE_CREATE})

    def build(self, _operation: ImageOperation, _invoker: object) -> App:
        """Build a placeholder provider app."""
        return App(name=self.name)


class CreateOnlyProvider:
    """Provider catalogue entry used to validate factory operations."""

    name = "example"

    catalogue = (
        make_model_definition(
            spec=make_model_spec(
                model_id="example/demo",
                operations=frozenset({ImageOperation.IMAGE_CREATE}),
            )
        ),
    )


class EditOnlyFactory(UnregisteredFactory):
    """Factory that declares an operation its provider does not support."""

    name = "example"
    operations = frozenset({ImageOperation.IMAGE_EDIT})


def _repository() -> ConfigRepository:
    return ConfigRepository(Path("/nonexistent/pixgen.toml"))


@pytest.fixture
def app() -> App:
    """Build a credential-free root app for parser tests."""
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))
    return build_app(
        ImageApplication(registry, Settings()),
        registry,
        (OpenAICliFactory(), GeminiCliFactory()),
        _repository(),
        OptimizeApplication(Settings()),
    )


def test_root_shared_create_accepts_repeated_models(app) -> None:
    command, bound, _ = app.parse_args(
        [
            "create",
            "--model",
            "openai/gpt-image-2",
            "--model",
            "gemini/gemini-3.1-flash-image",
            "A forest",
        ],
        print_error=False,
        exit_on_error=False,
    )

    assert command.__name__ == "create"
    assert bound.arguments["model"] == [
        "openai/gpt-image-2",
        "gemini/gemini-3.1-flash-image",
    ]


class TestRootVerbose:
    @pytest.mark.parametrize(
        ("tokens", "verbose", "rest"),
        [
            (["model", "list"], 0, ("model", "list")),
            (["-v", "model", "list"], 1, ("model", "list")),
            (["model", "list", "-vv"], 2, ("model", "list")),
            (
                ["--verbose", "optimize", "a.png", "--width", "8"],
                1,
                ("optimize", "a.png", "--width", "8"),
            ),
        ],
    )
    def test_launcher_counts_verbose_and_forwards_tokens(self, app, tokens, verbose, rest) -> None:
        _, bound, _ = app.meta.parse_args(tokens, print_error=False, exit_on_error=False)

        assert bound.arguments["verbose"] == verbose
        assert tuple(bound.arguments["tokens"]) == rest

    def test_launcher_configures_logging_before_dispatch(self, app, monkeypatch) -> None:
        calls: list[int] = []
        monkeypatch.setattr("pixgen.cli.app.configure_logging", calls.append)

        with contextlib.suppress(SystemExit):
            app.meta(["-vv", "model", "list"])

        assert calls == [2]


class TestRootOptimize:
    def test_registers_optimize_with_positional_source(self, app) -> None:
        command, bound, _ = app.parse_args(
            ["optimize", "source.png", "--width", "320", "--dry-run"],
            print_error=False,
            exit_on_error=False,
        )
        assert command.__name__ == "optimize"
        assert bound.arguments["source"] == Path("source.png")
        assert bound.arguments["width"] == [320]
        assert bound.arguments["dry_run"] is True

    def test_root_optimize_help_exits_successfully(self, app, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            app(["optimize", "--help"])
        assert exc_info.value.code == 0
        assert "--dry-run" in capsys.readouterr().out

    def test_main_uses_runtime_optimization_without_provider_clients(
        self, tmp_path, capsys, monkeypatch
    ) -> None:
        from pixgen.cli.app import main

        source = tmp_path / "source.png"
        with Image.new("RGB", (40, 20), "red") as image:
            image.save(source)
        settings = Settings.model_construct(
            openai_api_key=SecretStr("openai-test"), gemini_api_key=SecretStr("gemini-test")
        )
        monkeypatch.setattr(
            "sys.argv",
            [
                "pixgen",
                "optimize",
                str(source),
                "--width",
                "20",
                "--output",
                str(tmp_path / "output.png"),
                "--dry-run",
                "--json",
            ],
        )
        with (
            patch("pixgen.runtime.load_settings", return_value=settings),
            patch(
                "pixgen.providers.http.httpx2.AsyncClient.__init__", autospec=True
            ) as http_client,
            patch("google.genai.Client.__init__", autospec=True) as gemini_client,
            pytest.warns(UserWarning, match="Cyclopts application invoked without tokens"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["source_path"] == str(source)
        assert payload["variants"][0]["status"] == "planned"
        assert not Path(payload["variants"][0]["output_path"]).exists()
        http_client.assert_not_called()
        gemini_client.assert_not_called()


def test_root_group_create_accepts_repeated_models_and_metadata(app) -> None:
    command, bound, _ = app.parse_args(
        [
            "group",
            "create",
            "product-hero",
            "--model",
            "openai/gpt-image-2",
            "--model",
            "gemini/gemini-3.1-flash-image",
            "--description",
            "Product images",
            "--tag",
            "product",
        ],
        print_error=False,
        exit_on_error=False,
    )

    assert command.__name__ == "create"
    assert bound.arguments["name"] == "product-hero"
    assert bound.arguments["model"] == [
        "openai/gpt-image-2",
        "gemini/gemini-3.1-flash-image",
    ]
    assert bound.arguments["description"] == "Product images"
    assert bound.arguments["tag"] == ["product"]


@pytest.mark.parametrize(
    ("arguments", "command_name"),
    [
        (["create", "A forest"], "create"),
        (["edit", "--image", "source.png", "Add mist"], "edit"),
    ],
)
def test_shared_operations_keep_generation_feedback_internal(app, arguments, command_name) -> None:
    command, bound, _ = app.parse_args(arguments, print_error=False, exit_on_error=False)

    assert command.__name__ == command_name
    assert "verbose" not in bound.arguments
    assert "progress" not in bound.arguments


def test_root_provider_subcommand_owns_native_flags(app) -> None:
    command, bound, _ = app.parse_args(
        ["create", "openai", "--model", "gpt-image-2", "--quality", "high", "A forest"],
        print_error=False,
        exit_on_error=False,
    )

    assert command.__name__ == "create"
    assert bound.arguments["params"].quality == "high"


def test_provider_name_prompt_can_be_disambiguated_with_prompt_option(app) -> None:
    _command, bound, _ = app.parse_args(
        ["create", "--prompt", "openai"],
        print_error=False,
        exit_on_error=False,
    )

    assert bound.arguments["prompt"] == "openai"


def test_removed_image_group_and_raw_parameter_option_are_rejected(app) -> None:
    with pytest.raises(UnknownCommandError):
        app.parse_args(["image", "create", "A forest"], print_error=False, exit_on_error=False)
    with pytest.raises(UnknownOptionError):
        app.parse_args(
            ["create", "--param", "quality=high", "A forest"],
            print_error=False,
            exit_on_error=False,
        )


def test_root_app_rejects_factory_without_registered_provider() -> None:
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))

    with pytest.raises(ValueError, match="is not registered"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (OpenAICliFactory(), GeminiCliFactory(), UnregisteredFactory()),
            _repository(),
            OptimizeApplication(Settings()),
        )


def test_root_app_rejects_missing_provider_factory() -> None:
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))

    with pytest.raises(ValueError, match="lack CLI factories"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (OpenAICliFactory(),),
            _repository(),
            OptimizeApplication(Settings()),
        )


def test_root_app_rejects_duplicate_factory_names() -> None:
    registry = ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))

    with pytest.raises(ValueError, match="duplicate provider CLI name"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (OpenAICliFactory(), OpenAICliFactory(), GeminiCliFactory()),
            _repository(),
            OptimizeApplication(Settings()),
        )


def test_root_app_rejects_factory_operation_absent_from_provider() -> None:
    registry = ProviderRegistry((CreateOnlyProvider(),))

    with pytest.raises(ValueError, match="declares unsupported operations"):
        build_app(
            ImageApplication(registry, Settings()),
            registry,
            (EditOnlyFactory(),),
            _repository(),
            OptimizeApplication(Settings()),
        )


def test_main_renders_configuration_error_without_traceback(monkeypatch, capsys) -> None:
    from pixgen import runtime
    from pixgen.cli.app import main

    def fail_runtime(**_kwargs) -> None:
        raise PixgenError(ErrorCode.INVALID_CONFIGURATION, "bad config file")

    monkeypatch.setattr(runtime, "build_runtime", fail_runtime)
    monkeypatch.setattr("sys.argv", ["pixgen", "model", "list"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Error: bad config file" in captured.err
    assert "Traceback" not in captured.err


def test_root_model_get_reports_unknown_model_as_json(app, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(["model", "get", "nope/model", "--json"])

    assert exc_info.value.code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "model_not_found"


def test_root_model_list_exits_successfully(app, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(["model", "list", "--json"])

    assert exc_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["models"]


def test_root_model_ls_renders_tree(app, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(["model", "ls", "--tree"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "id: openai/gpt-image-2" in output
    assert "ops: image-create, image-edit" in output


def test_root_model_list_rejects_json_with_tree(app) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(["model", "list", "--json", "--tree"])

    assert exc_info.value.code == 1


class BrokenRegistry(ProviderRegistry):
    """Registry whose lookup fails with an unexpected bug."""

    def get_model(self, model_id: str) -> ModelSpec:
        raise RuntimeError(f"registry bug for {model_id}")


def test_model_get_does_not_relabel_unexpected_errors() -> None:
    registry = BrokenRegistry((OpenAIProvider(None), GeminiProvider(None)))
    app = build_model_app(registry)
    command, bound, _ = app.parse_args(
        ["get", "openai/gpt-image-2"], print_error=False, exit_on_error=False
    )

    with pytest.raises(RuntimeError, match="registry bug"):
        command(*bound.args, **bound.kwargs)


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--help"], id="help"),
        pytest.param(["--version"], id="version"),
        pytest.param(["create", "gemini", "--help"], id="subcommand-help"),
    ],
)
def test_root_builtins_exit_successfully(app, capsys, argv) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(argv)

    assert exc_info.value.code == 0
    assert capsys.readouterr().out


def test_root_without_arguments_renders_help(app, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app([])

    assert exc_info.value.code == 0
    assert "Usage: pixgen COMMAND" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "require_config_file"),
    [
        (["pixgen", "group", "create", "x"], False),
        (["pixgen", "group", "list"], False),
        (["pixgen", "model", "list"], True),
        (["pixgen", "create", "prompt"], True),
    ],
    ids=["group-create", "group-list", "model-list", "create"],
)
def test_main_only_relaxes_config_file_requirement_for_group_commands(
    monkeypatch, argv, require_config_file
) -> None:
    from pixgen import runtime
    from pixgen.cli.app import main

    seen: dict[str, bool] = {}

    def fake_runtime(*, require_config_file: bool = True) -> None:
        seen["value"] = require_config_file
        raise PixgenError(ErrorCode.INVALID_CONFIGURATION, "stop")

    monkeypatch.setattr(runtime, "build_runtime", fake_runtime)
    monkeypatch.setattr("sys.argv", argv)

    with pytest.raises(SystemExit):
        main()

    assert seen["value"] is require_config_file
