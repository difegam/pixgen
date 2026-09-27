"""Tests for core.params."""

import pytest

from pixgen.core.errors import PixgenError
from pixgen.core.params import parse_params


class TestParseParams:
    """Tests for --param parsing."""

    def test_unscoped_param(self) -> None:
        result = parse_params(['quality="high"'], {"openai/gpt-image-2"})
        assert None in result
        assert result[None]["quality"] == "high"

    def test_scoped_param(self) -> None:
        result = parse_params(
            ['openai/gpt-image-2:quality="high"'],
            {"openai/gpt-image-2"},
        )
        assert "openai/gpt-image-2" in result
        assert result["openai/gpt-image-2"]["quality"] == "high"

    def test_json_values(self) -> None:
        result = parse_params(
            ["size=1024", "ratio=1.5", "flag=true", "items=[1,2,3]"],
            {"openai/gpt-image-2"},
        )
        assert result[None]["size"] == 1024
        assert result[None]["ratio"] == 1.5
        assert result[None]["flag"] is True
        assert result[None]["items"] == [1, 2, 3]

    def test_rejects_nan(self) -> None:
        with pytest.raises(PixgenError, match="non-finite"):
            parse_params(["value=NaN"], {"openai/gpt-image-2"})

    def test_rejects_infinity(self) -> None:
        with pytest.raises(PixgenError, match="non-finite"):
            parse_params(["value=Infinity"], {"openai/gpt-image-2"})

    def test_rejects_negative_infinity(self) -> None:
        with pytest.raises(PixgenError, match="non-finite"):
            parse_params(["value=-Infinity"], {"openai/gpt-image-2"})

    @pytest.mark.parametrize("raw", ['value={"nested":1e400}', "value=[1e400]"])
    def test_rejects_nested_non_finite_values(self, raw: str) -> None:
        with pytest.raises(PixgenError, match="non-finite"):
            parse_params([raw], {"openai/gpt-image-2"})

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(PixgenError, match="invalid JSON"):
            parse_params(["value={bad}"], {"openai/gpt-image-2"})

    def test_rejects_missing_equals(self) -> None:
        with pytest.raises(PixgenError, match="must contain"):
            parse_params(["quality"], {"openai/gpt-image-2"})

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(PixgenError, match="name is empty"):
            parse_params(["=value"], {"openai/gpt-image-2"})

    def test_rejects_unselected_scope(self) -> None:
        with pytest.raises(PixgenError, match="does not match a selected model"):
            parse_params(
                ["openai/other:quality=high"],
                {"openai/gpt-image-2"},
            )

    def test_rejects_duplicate_unscoped(self) -> None:
        with pytest.raises(PixgenError, match="duplicate"):
            parse_params(
                ['quality="high"', 'quality="low"'],
                {"openai/gpt-image-2"},
            )

    def test_rejects_duplicate_scoped(self) -> None:
        with pytest.raises(PixgenError, match="duplicate"):
            parse_params(
                [
                    'openai/gpt-image-2:quality="high"',
                    'openai/gpt-image-2:quality="low"',
                ],
                {"openai/gpt-image-2"},
            )

    def test_rejects_same_name_scoped_and_unscoped(self) -> None:
        with pytest.raises(PixgenError, match="duplicate"):
            parse_params(
                ['quality="high"', 'openai/gpt-image-2:quality="low"'],
                {"openai/gpt-image-2"},
            )

    def test_multiple_params(self) -> None:
        result = parse_params(
            [
                'quality="high"',
                "openai/gpt-image-2:size=1024",
                'gemini/gemini-3.1-flash-image:aspect_ratio="16:9"',
            ],
            {"openai/gpt-image-2", "gemini/gemini-3.1-flash-image"},
        )
        assert result[None]["quality"] == "high"
        assert result["openai/gpt-image-2"]["size"] == 1024
        assert result["gemini/gemini-3.1-flash-image"]["aspect_ratio"] == "16:9"

    def test_empty_list(self) -> None:
        result = parse_params([], {"openai/gpt-image-2"})
        assert result == {}
