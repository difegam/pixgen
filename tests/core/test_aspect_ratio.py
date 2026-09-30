"""Tests for shared aspect-ratio validation."""

import pytest
from pydantic import ValidationError

from pixgen.core.aspect_ratio import AspectRatio, normalise_aspect_ratio


class TestAspectRatio:
    """Test canonical aspect-ratio values."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("32:18", "16:9"), ("2:2", "1:1"), ("21:9", "7:3"), ("7:5", "7:5")],
    )
    def test_normalises_positive_integer_ratios(self, value: str, expected: str) -> None:
        assert normalise_aspect_ratio(value) == expected

    @pytest.mark.parametrize(
        "value",
        ["0:1", "-1:2", "1.5:1", "16/9", "1:", ":1", "1:2:3", "", " 1:1"],
    )
    def test_rejects_invalid_ratios(self, value: str) -> None:
        with pytest.raises(ValueError, match="aspect ratio"):
            normalise_aspect_ratio(value)

    def test_pydantic_type_normalises_input(self) -> None:
        from pydantic import TypeAdapter

        assert TypeAdapter(AspectRatio).validate_python("21:9") == "7:3"
        with pytest.raises(ValidationError):
            TypeAdapter(AspectRatio).validate_python("1:0")
