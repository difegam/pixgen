"""Tests for artifact output planning."""

from typing import TYPE_CHECKING

import pytest

from pixgen.artifacts import OutputPlan, plan_output, save_artifact, write_atomic
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

    @pytest.mark.parametrize(
        ("model_id", "expected"),
        [
            ("openai/gpt-image-2", "openai-gpt-image-2-v1"),
            ("openrouter/meta/muse-image", "openrouter-meta-muse-image-v1"),
        ],
    )
    def test_generated_name_stays_in_output_dir(
        self, tmp_path: Path, model_id: str, expected: str
    ) -> None:
        (plan,) = plan_output(
            model_ids=[model_id],
            variants=1,
            output_dir=tmp_path,
            run_id="run1",
        )

        assert plan.path.parent == tmp_path
        assert expected in plan.path.name

    def test_rejects_existing_output_directory_file(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.write_bytes(b"file")

        with pytest.raises(PixgenError, match="directory"):
            plan_output(
                model_ids=["openai/gpt-image-2"],
                variants=1,
                output_dir=output_dir,
                run_id="run1",
            )

    def test_write_atomic_does_not_replace_without_overwrite(self, tmp_path: Path) -> None:
        path = tmp_path / "image.png"
        path.write_bytes(b"original")

        with pytest.raises(FileExistsError):
            write_atomic(path, b"replacement")

        assert path.read_bytes() == b"original"

    def test_write_atomic_replaces_with_overwrite(self, tmp_path: Path) -> None:
        path = tmp_path / "image.png"
        path.write_bytes(b"original")

        write_atomic(path, b"replacement", overwrite=True)

        assert path.read_bytes() == b"replacement"

    def test_save_artifact_preserves_explicit_path_and_warns(self, tmp_path: Path) -> None:
        path = tmp_path / "image.png"
        plan = OutputPlan(
            model_id="openai/gpt-image-2",
            variant=1,
            path=path,
            explicit_path=True,
        )

        result = save_artifact(plan, b"jpeg-bytes", "image/jpeg")

        assert result.path == path
        assert result.warnings
        assert path.read_bytes() == b"jpeg-bytes"
