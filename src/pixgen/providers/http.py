"""Provide shared HTTP client and image decoding helpers."""

import base64
import binascii
import logging
from typing import TYPE_CHECKING

import httpx2

from pixgen.core.errors import ErrorCode, ProviderError
from pixgen.providers.base import ProviderImage

__all__: list[str] = [
    "decode_base64_image",
    "log_provider_error",
    "make_http_client_factory",
]

logger = logging.getLogger(__name__)
_MAX_LOGGED_BODY = 500

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import SecretStr


def make_http_client_factory(
    api_key: SecretStr | None,
    *,
    base_url: str,
    request_timeout_seconds: int,
) -> Callable[[], httpx2.AsyncClient] | None:
    """Create a lazy factory for an authenticated HTTP client."""
    if not api_key:
        return None

    def make_client() -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=httpx2.Timeout(request_timeout_seconds),
        )

    return make_client


def decode_base64_image(
    encoded: str,
    *,
    media_type: str,
    provider_name: str,
) -> ProviderImage:
    """Validate and decode a provider's base64 image response safely."""
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ProviderError(
            ErrorCode.PROVIDER_FAILURE,
            f"{provider_name} returned an invalid image response",
        ) from exc

    if not image_bytes:
        raise ProviderError(
            ErrorCode.PROVIDER_FAILURE,
            f"{provider_name} returned an empty image",
        )

    return ProviderImage(image_bytes, media_type)


def log_provider_error(provider_name: str, exc: Exception) -> None:
    """Log the original provider failure before it is mapped to a public error.

    The summary (exception type and HTTP status) is logged at INFO. The response body,
    truncated, and the exception chain are logged at DEBUG only. Request payloads and
    headers are never logged.

    Args:
        provider_name: Display name of the provider.
        exc: Exception raised by the provider client.
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", getattr(exc, "code", None))
    logger.info("%s request failed: %s (status=%s)", provider_name, type(exc).__name__, status)
    if logger.isEnabledFor(logging.DEBUG):
        body = getattr(response, "text", None) or str(exc)
        logger.debug("%s failure detail: %s", provider_name, body[:_MAX_LOGGED_BODY], exc_info=exc)
