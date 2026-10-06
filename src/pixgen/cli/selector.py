"""Select curated models with deterministic fuzzy matching."""

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console

from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pixgen.core.models import ModelId, ModelSpec

__all__: list[str] = [
    "InteractiveGroupSelection",
    "InteractiveModelSelector",
    "ModelSelector",
    "filter_models",
    "fuzzy_rank",
    "prompt_group_metadata",
]


@dataclass(frozen=True, slots=True)
class InteractiveGroupSelection:
    """Hold models and metadata selected during group creation."""

    models: tuple[ModelId, ...]
    description: str
    tags: tuple[str, ...] = ()


@runtime_checkable
class ModelSelector(Protocol):
    """Select a complete model group from the available catalogue."""

    def select(
        self,
        models: tuple[ModelSpec, ...],
        *,
        description: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> InteractiveGroupSelection:
        """Select models and presentation metadata."""
        ...


@dataclass(slots=True)
class SelectionState:
    """Track selected model IDs for the line-oriented fallback selector."""

    models: tuple[ModelSpec, ...]
    _selected: set[ModelId] = field(default_factory=set, init=False, repr=False)

    def toggle(self, model_id: ModelId) -> None:
        """Toggle one model by canonical ID."""
        if model_id not in {model.id for model in self.models}:
            raise PixgenError(ErrorCode.INVALID_REQUEST, f"unknown model: {model_id}")
        if model_id in self._selected:
            self._selected.remove(model_id)
        else:
            self._selected.add(model_id)

    def selected_models(self) -> tuple[ModelId, ...]:
        """Return selected IDs in catalogue order."""
        return tuple(model.id for model in self.models if model.id in self._selected)

    def confirm(self) -> tuple[ModelId, ...]:
        """Confirm the selection, requiring at least one model."""
        selected = self.selected_models()
        if not selected:
            raise PixgenError(ErrorCode.INVALID_REQUEST, "at least one model must be selected")
        return selected


class InteractiveModelSelector:
    """Provide a terminal selector with a line-oriented fallback."""

    def __init__(
        self,
        *,
        console: Console | None = None,
        input_fn: Callable[[str], str] = input,
        fuzzy_prompt: Callable[..., Any] = inquirer.fuzzy,
        confirm_prompt: Callable[..., Any] = inquirer.confirm,
    ) -> None:
        self._console = console or Console()
        self._input_fn = input_fn
        self._fuzzy_prompt = fuzzy_prompt
        self._confirm_prompt = confirm_prompt

    def select(
        self,
        models: tuple[ModelSpec, ...],
        *,
        description: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> InteractiveGroupSelection:
        """Interactively select models and presentation metadata."""
        if not models:
            raise PixgenError(ErrorCode.INVALID_REQUEST, "no curated models are available")
        selected = (
            self._select_fuzzy(models) if _supports_raw_input() else self._select_lines(models)
        )
        description, tags = prompt_group_metadata(
            input_fn=self._input_fn,
            description=description,
            tags=tags,
        )
        if not self._confirm_prompt(
            message=f"Create group with {len(selected)} model(s)?",
            default=True,
        ).execute():
            raise PixgenError(ErrorCode.INVALID_REQUEST, "group creation cancelled")
        return InteractiveGroupSelection(models=selected, description=description, tags=tags)

    def _select_lines(self, models: tuple[ModelSpec, ...]) -> tuple[ModelId, ...]:
        query = self._input_fn("Filter models (blank for all): ")
        matches = filter_models(query, models)
        if not matches:
            raise PixgenError(ErrorCode.INVALID_REQUEST, f"no models match {query!r}")
        for index, model in enumerate(matches, start=1):
            self._console.print(f"{index}. {model.id} ({model.display_name})")
        raw_selection = self._input_fn("Select model numbers (comma-separated): ")
        state = SelectionState(models)
        for raw_index in raw_selection.split(","):
            try:
                index = int(raw_index.strip())
            except ValueError as exc:
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    "model selections must be numbers",
                ) from exc
            if not 1 <= index <= len(matches):
                raise PixgenError(ErrorCode.INVALID_REQUEST, "model selection is out of range")
            state.toggle(matches[index - 1].id)
        return state.confirm()

    def _select_fuzzy(self, models: tuple[ModelSpec, ...]) -> tuple[ModelId, ...]:
        choices = [
            Choice(value=model.id, name=f"{model.id} ({model.display_name})") for model in models
        ]
        result = self._fuzzy_prompt(
            message="Select models:",
            choices=choices,
            multiselect=True,
            border=True,
            instruction="(type to filter)",
            long_instruction="↑/↓ move · tab/space select · enter confirm",
            validate=lambda selection: len(selection) >= 1,
            invalid_message="select at least one model",
        ).execute()
        return tuple(result)


def fuzzy_rank(query: str, model: ModelSpec) -> tuple[int, int] | None:
    """Return a deterministic match rank for one model, or None."""
    needle = query.strip().casefold()
    if not needle:
        return (0, 0)
    candidates = (model.id.casefold(), model.display_name.casefold())
    best: tuple[int, int] | None = None
    for candidate_index, candidate in enumerate(candidates):
        if candidate == needle:
            rank = (0, candidate_index)
        elif candidate.startswith(needle):
            rank = (1, candidate_index)
        elif needle in candidate:
            rank = (2, candidate.index(needle))
        elif _is_subsequence(needle, candidate):
            rank = (3, len(candidate) - len(needle))
        else:
            continue
        if best is None or rank < best:
            best = rank
    return best


def filter_models(query: str, models: Sequence[ModelSpec]) -> tuple[ModelSpec, ...]:
    """Return matching models ordered by rank and then catalogue order."""
    ranked = (
        (rank, index, model)
        for index, model in enumerate(models)
        if (rank := fuzzy_rank(query, model)) is not None
    )
    return tuple(
        model for _rank, _index, model in sorted(ranked, key=lambda item: (item[0], item[1]))
    )


def prompt_group_metadata(
    *,
    input_fn: Callable[[str], str] = input,
    description: str | None = None,
    tags: tuple[str, ...] = (),
) -> tuple[str, tuple[str, ...]]:
    """Prompt for a required description and optional comma-separated tags."""
    clean_description = (
        description.strip() if description is not None else input_fn("Description: ").strip()
    )
    if not clean_description:
        raise PixgenError(ErrorCode.INVALID_REQUEST, "description must not be blank")
    clean_tags = tags or tuple(
        tag.strip()
        for tag in input_fn("Tags (comma-separated, optional): ").split(",")
        if tag.strip()
    )
    return clean_description, clean_tags


def _is_subsequence(needle: str, candidate: str) -> bool:
    iterator = iter(candidate)
    return all(character in iterator for character in needle)


def _supports_raw_input() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
