"""Tests for artifact output planning."""

from typing import TYPE_CHECKING

import pytest

from pixgen.artifacts import plan_output
from pixgen.core.errors import ErrorCode, PixgenError

if TYPE_CHECKING:
    from pathlib import Path


class TestPlanOutput:
    """Test output policy validation."""

    def test_rejects_output_and_output_dir_together(self, tmp_path: Path) -> None:
        with pytest.raises(PixgenError) as exc_info:
            plan_output(
                model_ids=["openai/gpt-image-2"],
                variants=1,
                output=tmp_path / "image.png",
                output_dir=tmp_path,
                run_id="run1",
            )

        assert exc_info.value.code == ErrorCode.INVALID_REQUEST

    def test_requires_mkdir_for_explicit_output_dir(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "renders"

        with pytest.raises(PixgenError, match="--mkdir"):
            plan_output(
                model_ids=["openai/gpt-image-2"],
                variants=1,
                output_dir=output_dir,
                run_id="run1",
            )

        assert not output_dir.exists()

    def test_rejects_declared_suffix_mismatch(self, tmp_path: Path) -> None:
        with pytest.raises(PixgenError, match="suffix"):
            plan_output(
                model_ids=["openai/gpt-image-2"],
                variants=1,
                output=tmp_path / "image.png",
                run_id="run1",
                declared_media_types={"openai/gpt-image-2": "image/jpeg"},
            )
