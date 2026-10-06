"""Look up the latest published Pixgen release."""

import httpx2

from pixgen.core.versioning import ReleaseInfo

__all__: list[str] = [
    "LATEST_RELEASE_URL",
    "fetch_latest_release",
]

LATEST_RELEASE_URL = "https://api.github.com/repos/difegam/pixgen/releases/latest"
_TIMEOUT_SECONDS = 3.0


def fetch_latest_release(client: httpx2.Client | None = None) -> ReleaseInfo | None:
    """Return the latest GitHub release, or None when it cannot be determined."""
    owns_client = client is None
    active = client or httpx2.Client(timeout=httpx2.Timeout(_TIMEOUT_SECONDS))
    try:
        response = active.get(
            LATEST_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        payload = response.json()
        return ReleaseInfo(tag=payload["tag_name"], url=payload["html_url"])
    except httpx2.HTTPError, ValueError, KeyError, TypeError:
        return None
    finally:
        if owns_client:
            active.close()
