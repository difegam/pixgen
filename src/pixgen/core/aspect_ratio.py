"""Validate and canonicalise shared image aspect ratios."""

import math
import re
from typing import Annotated

from pydantic import BeforeValidator, StringConstraints

__all__: list[str] = ["AspectRatio", "normalise_aspect_ratio"]

_RATIO_PATTERN = re.compile(r"([0-9]+):([0-9]+)\Z")


def normalise_aspect_ratio(value: str) -> str:
    """Return a canonical ratio from two positive decimal integers."""
    if not isinstance(value, str):
        raise ValueError("aspect ratio must be a string in width:height form")
    match = _RATIO_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("aspect ratio must use positive integers in width:height form")
    width, height = (int(component) for component in match.groups())
    if width < 1 or height < 1:
        raise ValueError("aspect ratio dimensions must be positive")
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


AspectRatio = Annotated[
    str,
    BeforeValidator(normalise_aspect_ratio),
    StringConstraints(pattern=r"^[1-9][0-9]*:[1-9][0-9]*$"),
]
