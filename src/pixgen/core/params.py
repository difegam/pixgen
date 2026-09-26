"""Parse and validate --param CLI values."""

import json
from typing import TYPE_CHECKING

from pixgen.core.errors import ErrorCode, PixgenError

__all__: list[str] = [
    "ParsedParam",
    "parse_params",
]

if TYPE_CHECKING:
    from pixgen.core.models import JsonValue


class ParsedParam:
    """A parsed --param value with optional model scope."""

    __slots__ = ("name", "scope", "value")

    def __init__(self, scope: str | None, name: str, value: JsonValue) -> None:
        self.scope = scope
        self.name = name
        self.value = value


def _reject_non_finite(value: float) -> None:
    if value != value or value == float("inf") or value == float("-inf"):  # noqa: PLR0124
        raise PixgenError(ErrorCode.INVALID_REQUEST, "non-finite parameter values are rejected")


def _parse_json_value(raw: str) -> JsonValue:
    def parse_constant(c: str) -> None:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"non-finite constant {c!r} is rejected",
        )

    try:
        value = json.loads(raw, parse_constant=parse_constant)
    except json.JSONDecodeError as exc:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST, f"invalid JSON in parameter value: {exc}"
        ) from exc

    if isinstance(value, float):
        _reject_non_finite(value)
    return value


def parse_params(
    raw_params: list[str],
    selected_models: set[str],
) -> dict[str | None, dict[str, JsonValue]]:
    """Parse --param values into scoped and unscoped parameter maps.

    Returns a dict keyed by scope (None for unscoped, ModelId for scoped).
    Raises PixgenError on invalid input.
    """
    result: dict[str | None, dict[str, JsonValue]] = {}
    seen_names: set[str] = set()

    for raw in raw_params:
        if "=" not in raw:
            raise PixgenError(ErrorCode.INVALID_REQUEST, f"parameter must contain '=': {raw!r}")

        left, _, right = raw.partition("=")
        left = left.strip()
        if not left:
            raise PixgenError(ErrorCode.INVALID_REQUEST, f"parameter name is empty: {raw!r}")

        if ":" in left:
            scope, _, name = left.partition(":")
            scope = scope.strip()
            name = name.strip()
            if scope not in selected_models:
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    f"parameter scope {scope!r} does not match a selected model",
                )
        else:
            scope = None
            name = left

        if not name:
            raise PixgenError(ErrorCode.INVALID_REQUEST, f"parameter name is empty: {raw!r}")

        if name in seen_names:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"duplicate parameter name: {name!r}",
            )
        seen_names.add(name)

        value = _parse_json_value(right)

        if scope not in result:
            result[scope] = {}
        result[scope][name] = value

    return result
