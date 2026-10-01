"""Select curated models with deterministic fuzzy matching."""

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rich.console import Console

from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pixgen.core.models import ModelId, ModelSpec

__all__: list[str] = [
    "InteractiveGroupSelection",
    "InteractiveModelSelector",
    "ModelSelector",
    "SelectionState",
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

    def select(self, models: tuple[ModelSpec, ...]) -> InteractiveGroupSelection:
        """Select models and presentation metadata."""
        ...


@dataclass(slots=True)
class SelectionState:
    """Track filtered rows, cursor position, and selected model IDs."""

    models: tuple[ModelSpec, ...]
    query: str = ""
    cursor: int = 0
    _selected: set[ModelId] = field(default_factory=set, init=False, repr=False)

    def set_query(self, query: str) -> None:
        """Set the filter query and reset the cursor."""
        self.query = query
        self.cursor = 0

    def filtered_models(self) -> tuple[ModelSpec, ...]:
        """Return models matching the current query."""
        return filter_models(self.query, self.models)

    def move_cursor(self, offset: int) -> None:
        """Move the cursor within the current filtered rows."""
        matches = self.filtered_models()
        if matches:
            self.cursor = max(0, min(self.cursor + offset, len(matches) - 1))

    def toggle(self, model_id: ModelId) -> None:
        """Toggle one model by canonical ID."""
        if model_id not in {model.id for model in self.models}:
            raise PixgenError(ErrorCode.INVALID_REQUEST, f"unknown model: {model_id}")
        if model_id in self._selected:
            self._selected.remove(model_id)
        else:
            self._selected.add(model_id)

    def toggle_cursor(self) -> None:
        """Toggle the model under the current cursor."""
        matches = self.filtered_models()
        if matches:
            self.toggle(matches[self.cursor].id)

    def selected_models(self) -> tuple[ModelId, ...]:
        """Return selected IDs in catalogue order."""
        return tuple(model.id for model in self.models if model.id in self._selected)

    def is_selected(self, model_id: ModelId) -> bool:
        """Return whether one model is selected."""
        return model_id in self._selected

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
    ) -> None:
        self._console = console or Console()
        self._input_fn = input_fn

    def select(self, models: tuple[ModelSpec, ...]) -> InteractiveGroupSelection:
        """Interactively select models and presentation metadata."""
        if not models:
            raise PixgenError(ErrorCode.INVALID_REQUEST, "no curated models are available")
        selected = self._select_raw(models) if _supports_raw_input() else self._select_lines(models)
        description, tags = prompt_group_metadata(input_fn=self._input_fn)
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

    def _select_raw(self, models: tuple[ModelSpec, ...]) -> tuple[ModelId, ...]:
        import termios
        import tty

        state = SelectionState(models)
        file_descriptor = sys.stdin.fileno()
        original_settings = termios.tcgetattr(file_descriptor)
        try:
            tty.setcbreak(file_descriptor)
            while True:
                self._render_raw(state)
                character = sys.stdin.read(1)
                if character in {"\r", "\n"}:
                    return state.confirm()
                if character == " ":
                    state.toggle_cursor()
                elif character == "\x7f":
                    state.set_query(state.query[:-1])
                elif character == "\x1b":
                    self._handle_escape_sequence(state)
                elif character.isprintable():
                    state.set_query(state.query + character)
        finally:
            termios.tcsetattr(file_descriptor, termios.TCSADRAIN, original_settings)

    def _handle_escape_sequence(self, state: SelectionState) -> None:
        sequence = sys.stdin.read(2)
        if sequence == "[A":
            state.move_cursor(-1)
        elif sequence == "[B":
            state.move_cursor(1)

    def _render_raw(self, state: SelectionState) -> None:
        self._console.clear()
        self._console.print("Filter models: " + state.query)
        matches = state.filtered_models()
        for index, model in enumerate(matches):
            marker = "☑" if state.is_selected(model.id) else "☐"
            cursor = ">" if index == state.cursor else " "
            self._console.print(f"{cursor} {marker} {model.id} ({model.display_name})")


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
) -> tuple[str, tuple[str, ...]]:
    """Prompt for a required description and optional comma-separated tags."""
    description = input_fn("Description: ").strip()
    if not description:
        raise PixgenError(ErrorCode.INVALID_REQUEST, "description must not be blank")
    tags = tuple(
        tag.strip()
        for tag in input_fn("Tags (comma-separated, optional): ").split(",")
        if tag.strip()
    )
    return description, tags


def _is_subsequence(needle: str, candidate: str) -> bool:
    iterator = iter(candidate)
    return all(character in iterator for character in needle)


def _supports_raw_input() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
