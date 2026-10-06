"""Tests for interactive model selection."""

from typing import TYPE_CHECKING

import pytest

from pixgen.cli.selector import (
    InteractiveGroupSelection,
    InteractiveModelSelector,
    ModelSelector,
    SelectionState,
    filter_models,
    fuzzy_rank,
    prompt_group_metadata,
)
from pixgen.core.errors import ErrorCode, PixgenError
from tests.factories import make_model_spec

if TYPE_CHECKING:
    from pixgen.core.models import ModelSpec


class TestFuzzyMatching:
    """Tests for deterministic model filtering."""

    def test_fuzzy_rank_orders_matches_deterministically(self) -> None:
        exact = make_model_spec(model_id="openai/gpt-image-2", display_name="GPT Image 2")
        prefix = make_model_spec(model_id="openai/gpt-image-pro", display_name="GPT Image Pro")
        substring = make_model_spec(model_id="openai/creative-image", display_name="Creative Image")
        no_match = make_model_spec(model_id="gemini/flash", display_name="Flash")

        exact_rank = fuzzy_rank("openai/gpt-image-2", exact)
        prefix_rank = fuzzy_rank("openai/gpt", prefix)
        substring_rank = fuzzy_rank("image", substring)

        assert exact_rank is not None
        assert prefix_rank is not None
        assert substring_rank is not None
        assert exact_rank < prefix_rank < substring_rank
        assert fuzzy_rank("missing", no_match) is None

    def test_filter_models_preserves_registry_order_for_equal_scores(self) -> None:
        models = (
            make_model_spec(model_id="openai/alpha", display_name="Model Alpha"),
            make_model_spec(model_id="gemini/beta", display_name="Model Beta"),
            make_model_spec(model_id="openai/gamma", display_name="Model Gamma"),
        )

        matches = filter_models("model", models)

        assert tuple(model.id for model in matches) == (
            "openai/alpha",
            "gemini/beta",
            "openai/gamma",
        )


class TestSelectionState:
    """Tests for keyboard-independent selection state."""

    def test_selected_models_preserve_display_order(self) -> None:
        models = (
            make_model_spec(model_id="openai/alpha", display_name="Alpha"),
            make_model_spec(model_id="gemini/beta", display_name="Beta"),
        )
        state = SelectionState(models)

        state.toggle("gemini/beta")
        state.toggle("openai/alpha")

        assert state.selected_models() == ("openai/alpha", "gemini/beta")

    def test_confirm_rejects_empty_selection(self) -> None:
        models = (make_model_spec(model_id="openai/alpha", display_name="Alpha"),)
        state = SelectionState(models)

        with pytest.raises(PixgenError) as exc_info:
            state.confirm()

        assert exc_info.value.code is ErrorCode.INVALID_REQUEST


def test_metadata_prompt_returns_trimmed_description_and_tags() -> None:
    answers = iter([" Product images ", " product, marketing "])

    description, tags = prompt_group_metadata(input_fn=lambda _prompt: next(answers))

    assert description == "Product images"
    assert tags == ("product", "marketing")


class TestFuzzySelection:
    """Tests for the InquirerPy-backed interactive selection path."""

    def test_select_fuzzy_returns_selection_on_confirm(self) -> None:
        models = (
            make_model_spec(model_id="openai/alpha", display_name="Alpha"),
            make_model_spec(model_id="gemini/beta", display_name="Beta"),
        )
        answers = iter(["Product images", "product, marketing"])
        fake_fuzzy = _FakeFuzzyPrompt(result=["openai/alpha"])
        fake_confirm = _FakeConfirmPrompt(result=True)
        selector = InteractiveModelSelector(
            input_fn=lambda _prompt: next(answers),
            fuzzy_prompt=fake_fuzzy,
            confirm_prompt=fake_confirm,
        )

        selection = selector._select_fuzzy(models)

        assert selection == ("openai/alpha",)
        assert fake_fuzzy.calls[0]["multiselect"] is True
        assert fake_fuzzy.calls[0]["border"] is True
        assert fake_fuzzy.calls[0]["long_instruction"]
        assert [choice.value for choice in fake_fuzzy.calls[0]["choices"]] == [
            "openai/alpha",
            "gemini/beta",
        ]

    def test_select_raises_when_confirmation_declined(self) -> None:
        models = (make_model_spec(model_id="openai/alpha", display_name="Alpha"),)
        # non-TTY path: filter query, selection index, description, tags.
        answers = iter(["", "1", "Product images", ""])
        selector = InteractiveModelSelector(
            input_fn=lambda _prompt: next(answers),
            fuzzy_prompt=_FakeFuzzyPrompt(result=["openai/alpha"]),
            confirm_prompt=_FakeConfirmPrompt(result=False),
        )

        with pytest.raises(PixgenError) as exc_info:
            selector.select(models)

        assert exc_info.value.code is ErrorCode.INVALID_REQUEST


class _FakeFuzzyPrompt:
    """Record calls and return a canned fuzzy-selection result."""

    def __init__(self, *, result: list[str]) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> _FakeExecutable:
        self.calls.append(kwargs)
        return _FakeExecutable(self._result)


class _FakeConfirmPrompt:
    """Record calls and return a canned confirmation result."""

    def __init__(self, *, result: bool) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> _FakeExecutable:
        self.calls.append(kwargs)
        return _FakeExecutable(self._result)


class _FakeExecutable:
    """Mimic an InquirerPy prompt's `.execute()` return value."""

    def __init__(self, result: object) -> None:
        self._result = result

    def execute(self) -> object:
        return self._result


def test_fake_selector_can_return_complete_selection() -> None:
    class FakeSelector:
        def select(
            self,
            models: tuple[ModelSpec, ...],
            *,
            description: str | None = None,
            tags: tuple[str, ...] = (),
        ) -> InteractiveGroupSelection:
            del models
            return InteractiveGroupSelection(
                models=("openai/gpt-image-2",),
                description=description or "Product images",
                tags=tags or ("product",),
            )

    selector = FakeSelector()

    assert isinstance(selector, ModelSelector)
    assert selector.select(()).models == ("openai/gpt-image-2",)
