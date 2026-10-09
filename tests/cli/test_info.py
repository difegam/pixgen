from typing import TYPE_CHECKING

import pytest

from pixgen.cli.info import _mask_secret, _secret_env_names, build_info_command
from pixgen.core.versioning import ReleaseInfo

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pixgen.cli.info.resolve_config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr("pixgen.cli.info.resolve_env_file_path", lambda: tmp_path / ".env")
    monkeypatch.setattr("pixgen.cli.info._installed_version", lambda: "0.1.0")
    for name in (
        "PIXGEN_CONFIG",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "PIXGEN_OPENAI_API_KEY",
        "PIXGEN_GEMINI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _release(tag: str) -> ReleaseInfo:
    return ReleaseInfo(tag=tag, url="https://example.test/release")


class TestInfoCommand:
    def test_shows_sections_and_paths(self, capsys, tmp_path) -> None:
        build_info_command(lambda: _release("v0.1.0"))()
        out = capsys.readouterr().out
        assert "Version info:" in out
        assert "Config files:" in out
        assert "Env vars:" in out
        assert f"{tmp_path / 'config.toml'} (missing)" in out

    def test_marks_existing_files_found(self, capsys, tmp_path) -> None:
        (tmp_path / ".env").write_text("")
        build_info_command(lambda: None)()
        assert f"{tmp_path / '.env'} (found)" in capsys.readouterr().out

    def test_update_available(self, capsys) -> None:
        build_info_command(lambda: _release("v0.2.0"))()
        out = capsys.readouterr().out
        assert "update available: v0.2.0" in out
        assert "https://example.test/release" in out

    def test_up_to_date(self, capsys) -> None:
        build_info_command(lambda: _release("v0.1.0"))()
        assert "up to date" in capsys.readouterr().out

    def test_check_failure_is_not_fatal(self, capsys) -> None:
        build_info_command(lambda: None)()
        assert "could not check for updates" in capsys.readouterr().out

    def test_no_check_skips_lookup(self, capsys) -> None:
        def explode() -> ReleaseInfo:
            raise AssertionError("lookup must be skipped")

        build_info_command(explode)(check=False)
        assert "update:" not in capsys.readouterr().out

    def test_long_secret_shows_only_suffix(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-1234")
        build_info_command(lambda: None)()
        out = capsys.readouterr().out
        assert "sk-super-secret-1234" not in out
        assert "sk-" not in out
        assert "OPENAI_API_KEY: ********1234" in out
        assert "GEMINI_API_KEY: not set" in out

    def test_short_secret_is_fully_masked(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "abcd1234")
        build_info_command(lambda: None)()
        out = capsys.readouterr().out
        assert "abcd" not in out
        assert "1234" not in out
        assert "OPENAI_API_KEY: ********" in out

    def test_empty_secret_is_not_set(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "")
        build_info_command(lambda: None)()
        assert "OPENAI_API_KEY: not set" in capsys.readouterr().out

    @pytest.mark.parametrize("name", ["PIXGEN_OPENAI_API_KEY", "PIXGEN_GEMINI_API_KEY"])
    def test_prefixed_alias_is_checked_and_masked(self, capsys, monkeypatch, name) -> None:
        monkeypatch.setenv(name, "sk-alias-secret-9876")
        build_info_command(lambda: None)()
        out = capsys.readouterr().out
        assert f"{name}: ********9876" in out
        assert "sk-alias-secret" not in out

    def test_alias_and_plain_name_both_listed(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("PIXGEN_OPENAI_API_KEY", "aaaaaaaaaaaa1111")
        monkeypatch.setenv("OPENAI_API_KEY", "bbbbbbbbbbbb2222")
        build_info_command(lambda: None)()
        out = capsys.readouterr().out
        assert "PIXGEN_OPENAI_API_KEY: ********1111" in out
        assert "\nOPENAI_API_KEY: ********2222" in out

    def test_listed_names_match_settings_aliases(self) -> None:
        assert _secret_env_names() == (
            "PIXGEN_OPENAI_API_KEY",
            "OPENAI_API_KEY",
            "PIXGEN_GEMINI_API_KEY",
            "GEMINI_API_KEY",
        )


class TestMaskSecret:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("sk-super-secret-1234", "********1234"),
            ("123456789", "*****6789"),
            ("12345678", "********"),
            ("abc", "***"),
        ],
        ids=["long-capped", "just-over", "boundary", "short"],
    )
    def test_mask(self, value, expected) -> None:
        assert _mask_secret(value).plain == expected
