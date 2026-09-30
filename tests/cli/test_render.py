import uuid
from io import StringIO

import pytest
from rich.console import Console

from pixgen.cli import render
from pixgen.core.errors import ErrorCode
from pixgen.core.models import ImageOperation
from pixgen.core.results import CommandResult, ModelListResult, PublicError, TargetResult
from tests.factories import make_model_spec


def _console(*, interactive: bool) -> Console:
    return Console(
        file=StringIO(),
        force_terminal=interactive,
        force_interactive=interactive,
        highlight=False,
        markup=False,
        record=True,
        width=120,
    )


def _mixed_result() -> CommandResult:
    return CommandResult(
        run_id=uuid.uuid7(),
        results=(
            TargetResult(
                model="fake/literal",
                variant=1,
                artifact_path="output/[literal].png",
                media_type="image/png",
                warnings=("literal [warning]",),
            ),
            TargetResult(
                model="fake/failed",
                variant=2,
                error=PublicError(
                    code=ErrorCode.PROVIDER_FAILURE,
                    message="literal [error]",
                ),
            ),
        ),
    )


def test_render_command_result_uses_table_for_interactive_terminal(monkeypatch) -> None:
    stdout = _console(interactive=True)
    stderr = _console(interactive=True)
    monkeypatch.setattr(render, "_stdout_console", stdout)
    monkeypatch.setattr(render, "_stderr_console", stderr)

    render.render_command_result(_mixed_result(), as_json=False)

    output = stdout.export_text()
    assert "Model" in output
    assert "Variant" in output
    assert "Status" in output
    assert "fake/literal" in output
    assert "output/[literal].png" in output
    assert "literal [warning]" in output
    assert "fake/failed" in output
    assert "literal [error]" in output


def test_render_command_result_shows_default_output_relative_to_current_directory(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    stdout = _console(interactive=True)
    monkeypatch.setattr(render, "_stdout_console", stdout)
    monkeypatch.setattr(render, "_stderr_console", _console(interactive=True))
    artifact_path = tmp_path / "pixgen" / "image.png"
    result = CommandResult(
        run_id=uuid.uuid7(),
        results=(
            TargetResult(
                model="fake/model",
                variant=1,
                artifact_path=artifact_path,
                media_type="image/png",
            ),
        ),
    )

    render.render_command_result(result, as_json=False, relative_output_paths=True)

    output = stdout.export_text()
    assert "pixgen/image.png" in output
    assert str(artifact_path) not in output


def test_render_command_result_preserves_plain_output_when_not_interactive(monkeypatch) -> None:
    stdout = _console(interactive=False)
    stderr = _console(interactive=False)
    monkeypatch.setattr(render, "_stdout_console", stdout)
    monkeypatch.setattr(render, "_stderr_console", stderr)

    render.render_command_result(_mixed_result(), as_json=False)

    stdout_output = stdout.export_text()
    stderr_output = stderr.export_text()
    assert "Run ID:" in stdout_output
    assert "fake/literal v1: output/[literal].png" in stdout_output
    assert "fake/failed v2: literal [error]" in stderr_output


def test_create_generation_progress_excludes_json_and_noninteractive_output(monkeypatch) -> None:
    monkeypatch.setattr(render, "_stdout_console", _console(interactive=False))
    monkeypatch.setattr(render, "_stderr_console", _console(interactive=False))

    assert render.create_generation_progress(as_json=True) is None
    assert render.create_generation_progress(as_json=False) is None


@pytest.mark.parametrize(
    ("stdout_interactive", "stderr_interactive"), [(False, True), (True, False)]
)
def test_create_generation_progress_requires_both_interactive_streams(
    monkeypatch, stdout_interactive, stderr_interactive
) -> None:
    monkeypatch.setattr(render, "_stdout_console", _console(interactive=stdout_interactive))
    monkeypatch.setattr(render, "_stderr_console", _console(interactive=stderr_interactive))

    assert render.create_generation_progress(as_json=False) is None


def _model_list_result() -> ModelListResult:
    return ModelListResult(
        models=(
            make_model_spec(),
            make_model_spec(
                model_id="gemini/gemini-3-pro-image",
                display_name="Gemini [Literal]",
                operations=frozenset({ImageOperation.IMAGE_CREATE}),
            ),
        )
    )


class TestRenderModelListResult:
    """Tests for model list rendering."""

    def test_renders_table_by_default(self, monkeypatch) -> None:
        stdout = _console(interactive=False)
        monkeypatch.setattr(render, "_stdout_console", stdout)

        render.render_model_list_result(_model_list_result(), as_json=False)

        output = stdout.export_text()
        for header in ("Provider", "Model", "ID", "Operations"):
            assert header in output
        assert "openai/gpt-image-2" in output
        assert "GPT Image 2" in output
        assert "image-create, image-edit" in output
        assert "gemini/gemini-3-pro-image" in output
        assert "Gemini [Literal]" in output

    def test_renders_tree_grouped_by_provider(self, monkeypatch) -> None:
        stdout = _console(interactive=False)
        monkeypatch.setattr(render, "_stdout_console", stdout)

        render.render_model_list_result(_model_list_result(), as_json=False, as_tree=True)

        output = stdout.export_text()
        lines = output.splitlines()
        assert lines[0].strip() == "openai"
        assert "└── GPT Image 2" in output
        assert "├── id: openai/gpt-image-2" in output
        assert "└── ops: image-create, image-edit" in output
        assert "gemini" in lines
        assert "id: gemini/gemini-3-pro-image" in output
        assert "ops: image-create" in output
        assert "Operations" not in output

    def test_json_output_ignores_layout(self, monkeypatch, capsys) -> None:
        stdout = _console(interactive=False)
        monkeypatch.setattr(render, "_stdout_console", stdout)
        result = _model_list_result()

        render.render_model_list_result(result, as_json=True)

        assert capsys.readouterr().out == result.model_dump_json(indent=2) + "\n"
        assert stdout.export_text() == ""
