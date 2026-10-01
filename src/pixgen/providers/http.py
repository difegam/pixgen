"""Provide shared HTTP client and image decoding helpers."""

import base64
import binascii
from typing import TYPE_CHECKING

import httpx2

from pixgen.core.errors import ErrorCode, ProviderError
from pixgen.providers.base import ProviderImage

__all__: list[str] = [
    "decode_base64_image",
    "make_http_client_factory",
]

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
    if api_key is None:
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
