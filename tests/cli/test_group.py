"""Tests for the model-group creation command."""

import json
from typing import TYPE_CHECKING

import pytest

from pixgen.cli.group import build_group_app
from pixgen.cli.outcome import CliOutcome, exit_status, render_outcome
from pixgen.cli.selector import InteractiveGroupSelection
from pixgen.config.models import ModelGroup
from pixgen.config.writer import ConfigRepository
from pixgen.core.errors import ErrorCode
from pixgen.core.results import GroupCreateResult, GroupListResult
from pixgen.providers.gemini import GeminiProvider
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from collections.abc import Callable
    from inspect import BoundArguments
    from pathlib import Path

    from cyclopts import App


class RecordingRepository:
    """Capture group writes for command tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.groups: list[tuple[str, ModelGroup]] = []

    def create_group(self, name: str, group: ModelGroup) -> None:
        self.groups.append((name, group))


class RecordingSelector:
    """Return a known interactive selection."""

    def __init__(self) -> None:
        self.called = False

    def select(
        self,
        _models,
        *,
        description: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> InteractiveGroupSelection:
        del description, tags
        self.called = True
        return InteractiveGroupSelection(
            models=("openai/gpt-image-2",),
            description="Interactive images",
            tags=("interactive",),
        )


class MetadataRecordingSelector:
    """Capture metadata supplied to interactive selection."""

    def __init__(self) -> None:
        self.metadata = None

    def select(
        self,
        _models,
        *,
        description: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> InteractiveGroupSelection:
        self.metadata = (description, tags)
        return InteractiveGroupSelection(
            models=("openai/gpt-image-2",),
            description=description or "Prompted description",
            tags=tags,
        )


class NeverSelector:
    """Fail if non-interactive command execution reaches the selector."""

    def select(self, _models: tuple[object, ...]) -> InteractiveGroupSelection:
        pytest.fail("selector must not be called for non-interactive creation")


def _registry() -> ProviderRegistry:
    return ProviderRegistry((OpenAIProvider(None), GeminiProvider(None)))


def _parse(app: App, argv: list[str]) -> tuple[Callable[..., object], BoundArguments]:
    command, bound, _ = app.parse_args(argv, print_error=False, exit_on_error=False)
    return command, bound


def test_explicit_models_preserve_order_and_metadata(tmp_path: Path) -> None:
    repository = RecordingRepository(tmp_path / "config.toml")
    app = build_group_app(_registry(), repository)
    command, bound = _parse(
        app,
        [
            "create",
            "product-hero",
            "--model",
            "gemini/gemini-3.1-flash-image",
            "--model",
            "openai/gpt-image-2",
            "--description",
            "Product images",
            "--tag",
            "product",
            "--tag",
            "marketing",
        ],
    )

    outcome = command(*bound.args, **bound.kwargs)

    assert exit_status(outcome.result).value == 0
    name, group = repository.groups[0]
    assert name == "product-hero"
    assert group.models == ("gemini/gemini-3.1-flash-image", "openai/gpt-image-2")
    assert group.description == "Product images"
    assert group.tags == ("product", "marketing")


def test_explicit_creation_requires_description(tmp_path: Path) -> None:
    repository = RecordingRepository(tmp_path / "config.toml")
    app = build_group_app(_registry(), repository)
    command, bound = _parse(app, ["create", "product-hero", "--model", "openai/gpt-image-2"])

    outcome = command(*bound.args, **bound.kwargs)

    assert exit_status(outcome.result).name == "REJECTED"
    assert outcome.result.error is not None
    assert outcome.result.error.code is ErrorCode.INVALID_REQUEST
    assert repository.groups == []


def test_create_group_rejects_unknown_model_without_writing(tmp_path: Path) -> None:
    repository = RecordingRepository(tmp_path / "config.toml")
    selector = NeverSelector()
    app = build_group_app(_registry(), repository, selector)
    command, bound = _parse(
        app,
        ["create", "product-hero", "--model", "openai/missing", "--description", "Images"],
    )

    outcome = command(*bound.args, **bound.kwargs)

    assert outcome.result.error is not None
    assert outcome.result.error.code is ErrorCode.MODEL_NOT_FOUND
    assert repository.groups == []


def test_interactive_creation_delegates_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = RecordingRepository(tmp_path / "config.toml")
    selector = RecordingSelector()
    monkeypatch.setattr("pixgen.cli.group._is_interactive_terminal", lambda: True)
    app = build_group_app(_registry(), repository, selector)
    command, bound = _parse(app, ["create", "product-hero"])

    outcome = command(*bound.args, **bound.kwargs)

    assert outcome.result.error is None
    assert selector.called is True
    assert repository.groups[0][1].description == "Interactive images"


def test_interactive_creation_preserves_provided_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = RecordingRepository(tmp_path / "config.toml")
    selector = MetadataRecordingSelector()
    monkeypatch.setattr("pixgen.cli.group._is_interactive_terminal", lambda: True)
    app = build_group_app(_registry(), repository, selector)
    command, bound = _parse(
        app,
        [
            "create",
            "product-hero",
            "--description",
            "Provided description",
            "--tag",
            "provided",
        ],
    )

    outcome = command(*bound.args, **bound.kwargs)

    assert outcome.result.error is None
    assert selector.metadata == ("Provided description", ("provided",))
    assert repository.groups[0][1].description == "Provided description"
    assert repository.groups[0][1].tags == ("provided",)


def test_create_group_requires_models_when_noninteractive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = RecordingRepository(tmp_path / "config.toml")
    monkeypatch.setattr("pixgen.cli.group._is_interactive_terminal", lambda: False)
    app = build_group_app(_registry(), repository, NeverSelector())
    command, bound = _parse(app, ["create", "product-hero"])

    outcome = command(*bound.args, **bound.kwargs)

    assert outcome.result.error is not None
    assert outcome.result.error.code is ErrorCode.INVALID_REQUEST
    assert repository.groups == []


def test_create_group_json_requires_models_even_in_interactive_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = RecordingRepository(tmp_path / "config.toml")
    monkeypatch.setattr("pixgen.cli.group._is_interactive_terminal", lambda: True)
    app = build_group_app(_registry(), repository, NeverSelector())
    command, bound = _parse(app, ["create", "product-hero", "--json"])

    outcome = command(*bound.args, **bound.kwargs)

    assert outcome.result.error is not None
    assert outcome.result.error.code is ErrorCode.INVALID_REQUEST
    assert "--json" in outcome.result.error.message
    assert repository.groups == []


def test_duplicate_group_name_returns_invalid_request(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """[groups.product-hero]
description = "Original"
tags = []
models = ["openai/gpt-image-2"]
"""
    )
    repository = ConfigRepository(config_path)
    app = build_group_app(_registry(), repository)
    command, bound = _parse(
        app,
        ["create", "product-hero", "--model", "openai/gpt-image-2", "--description", "New"],
    )

    outcome = command(*bound.args, **bound.kwargs)

    assert outcome.result.error is not None
    assert outcome.result.error.code is ErrorCode.INVALID_REQUEST
    assert "pixgen group edit product-hero" in outcome.result.error.message
    assert exit_status(outcome.result) == 2
    assert "Original" in config_path.read_text()


def _seeded_repository(tmp_path: Path) -> ConfigRepository:
    repository = ConfigRepository(tmp_path / "config.toml")
    repository.create_group(
        "fast",
        ModelGroup(
            models=("openai/gpt-image-2", "gemini/gemini-3.1-flash-image"),
            description="Quick drafts",
            tags=("draft", "cheap"),
        ),
    )
    return repository


@pytest.mark.parametrize("alias", ["list", "ls"])
def test_group_list_aliases_return_group_summaries(tmp_path: Path, alias: str) -> None:
    app = build_group_app(_registry(), _seeded_repository(tmp_path))
    command, bound = _parse(app, [alias])

    outcome = command(*bound.args, **bound.kwargs)

    assert isinstance(outcome.result, GroupListResult)
    (summary,) = outcome.result.groups
    assert summary.name == "fast"
    assert summary.description == "Quick drafts"
    assert summary.tags == ("draft", "cheap")
    assert summary.models == ("openai/gpt-image-2", "gemini/gemini-3.1-flash-image")


def test_group_list_renders_tree_with_details(tmp_path: Path, capsys) -> None:
    app = build_group_app(_registry(), _seeded_repository(tmp_path))
    command, bound = _parse(app, ["list"])

    render_outcome(command(*bound.args, **bound.kwargs))

    out = capsys.readouterr().out
    assert "fast" in out
    assert "description: Quick drafts" in out
    assert "tags: draft, cheap" in out
    assert "openai/gpt-image-2" in out
    assert "gemini/gemini-3.1-flash-image" in out
    assert "├──" in out or "└──" in out


def test_group_list_reports_when_empty(tmp_path: Path, capsys) -> None:
    app = build_group_app(_registry(), ConfigRepository(tmp_path / "config.toml"))
    command, bound = _parse(app, ["ls"])

    render_outcome(command(*bound.args, **bound.kwargs))

    assert "No model groups configured." in capsys.readouterr().out


def test_group_list_json(tmp_path: Path, capsys) -> None:
    app = build_group_app(_registry(), _seeded_repository(tmp_path))
    command, bound = _parse(app, ["list", "--json"])

    render_outcome(command(*bound.args, **bound.kwargs))

    payload = json.loads(capsys.readouterr().out)
    assert payload["groups"][0]["name"] == "fast"
    assert payload["groups"][0]["models"][0] == "openai/gpt-image-2"


def test_json_result_excludes_group_metadata(tmp_path: Path, capsys) -> None:
    result = GroupCreateResult(name="product-hero", config_path=tmp_path / "config.toml")

    render_outcome(CliOutcome(result, as_json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "product-hero"
    assert "description" not in payload
    assert "tags" not in payload
