"""Compare release versions using semantic versioning."""

from enum import StrEnum

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field

__all__: list[str] = [
    "ReleaseInfo",
    "UpdateStatus",
    "compare_versions",
    "parse_version",
]


class UpdateStatus(StrEnum):
    """Describe how the installed version relates to the latest release."""

    UP_TO_DATE = "UP_TO_DATE"
    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    AHEAD = "AHEAD"
    UNKNOWN = "UNKNOWN"


class ReleaseInfo(BaseModel):
    """Describe a published release."""

    model_config = ConfigDict(frozen=True)

    tag: str = Field(description="Release tag, optionally prefixed with 'v'")
    url: str = Field(description="Release page URL")


def parse_version(value: str) -> Version | None:
    """Parse a version or tag such as 'v1.2.3', returning None when invalid."""
    try:
        return Version(value.strip().removeprefix("v"))
    except InvalidVersion:
        return None


def compare_versions(current: str, latest: str) -> UpdateStatus:
    """Compare the installed version with the latest release version."""
    installed = parse_version(current)
    released = parse_version(latest)
    if installed is None or released is None:
        return UpdateStatus.UNKNOWN
    if released > installed:
        return UpdateStatus.UPDATE_AVAILABLE
    if released < installed:
        return UpdateStatus.AHEAD
    return UpdateStatus.UP_TO_DATE
