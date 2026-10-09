import pytest

from pixgen.core.versioning import UpdateStatus, compare_versions, parse_version


class TestParseVersion:
    @pytest.mark.parametrize("value", ["1.2.3", "v1.2.3", " v1.2.3 "], ids=["bare", "v", "space"])
    def test_accepts_release_tags(self, value) -> None:
        version = parse_version(value)
        assert version is not None
        assert str(version) == "1.2.3"

    @pytest.mark.parametrize("value", ["", "latest", "vx.y"], ids=["empty", "word", "garbage"])
    def test_rejects_invalid(self, value) -> None:
        assert parse_version(value) is None


class TestCompareVersions:
    @pytest.mark.parametrize(
        ("current", "latest", "expected"),
        [
            ("0.1.0", "v0.2.0", UpdateStatus.UPDATE_AVAILABLE),
            ("0.1.0", "0.1.0", UpdateStatus.UP_TO_DATE),
            ("0.2.0", "v0.1.0", UpdateStatus.AHEAD),
            ("0.9.0", "v0.10.0", UpdateStatus.UPDATE_AVAILABLE),
            ("1.0.0rc1", "v1.0.0", UpdateStatus.UPDATE_AVAILABLE),
            ("unknown", "v1.0.0", UpdateStatus.UNKNOWN),
            ("1.0.0", "nightly", UpdateStatus.UNKNOWN),
        ],
        ids=["newer", "equal", "ahead", "numeric", "prerelease", "bad-current", "bad-latest"],
    )
    def test_compare(self, current, latest, expected) -> None:
        assert compare_versions(current, latest) is expected
