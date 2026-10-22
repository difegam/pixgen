"""Tests for shared provider HTTP helpers."""

import base64

import pytest
from pydantic import SecretStr

from pixgen.core.errors import ErrorCode, ProviderError
from pixgen.providers import http
from pixgen.providers.base import ProviderImage


class TestMakeHttpClientFactory:
    """Tests for lazy authenticated HTTP client construction."""

    def test_returns_none_without_key(self) -> None:
        assert (
            http.make_http_client_factory(
                None,
                base_url="https://api.example.test/v1",
                request_timeout_seconds=12,
            )
            is None
        )

    def test_returns_none_for_empty_key(self) -> None:
        assert (
            http.make_http_client_factory(
                SecretStr(""),
                base_url="https://api.example.test/v1",
                request_timeout_seconds=12,
            )
            is None
        )

    def test_creates_authenticated_client_lazily(self, monkeypatch) -> None:
        calls: list[dict[str, object]] = []
        transport_calls: list[dict[str, object]] = []
        transport = object()

        def make_client(**kwargs: object) -> object:
            calls.append(kwargs)
            return object()

        def make_transport(**kwargs: object) -> object:
            transport_calls.append(kwargs)
            return transport

        monkeypatch.setattr(http.httpx2, "AsyncClient", make_client)
        monkeypatch.setattr(http.httpx2, "AsyncHTTPTransport", make_transport)
        factory = http.make_http_client_factory(
            SecretStr("test-key"),
            base_url="https://api.example.test/v1",
            request_timeout_seconds=12,
            request_retries=3,
        )

        assert factory is not None
        assert calls == []
        factory()

        assert calls == [
            {
                "base_url": "https://api.example.test/v1",
                "headers": {"Authorization": "Bearer test-key"},
                "timeout": http.httpx2.Timeout(12),
                "transport": transport,
            }
        ]
        assert transport_calls == [{"retries": 3}]

    def test_transport_retries_default_to_zero(self, monkeypatch) -> None:
        transport_calls: list[dict[str, object]] = []
        monkeypatch.setattr(http.httpx2, "AsyncClient", lambda **_kwargs: object())
        monkeypatch.setattr(
            http.httpx2,
            "AsyncHTTPTransport",
            lambda **kwargs: transport_calls.append(kwargs) or object(),
        )
        factory = http.make_http_client_factory(
            SecretStr("test-key"),
            base_url="https://api.example.test/v1",
            request_timeout_seconds=12,
        )

        assert factory is not None
        factory()

        assert transport_calls == [{"retries": 0}]


class TestDecodeBase64Image:
    """Tests for safe image response decoding."""

    def test_returns_bytes_and_media_type(self) -> None:
        image = http.decode_base64_image(
            base64.b64encode(b"image bytes").decode(),
            media_type="image/webp",
            provider_name="TestProvider",
        )

        assert image == ProviderImage(data=b"image bytes", media_type="image/webp")

    @pytest.mark.parametrize("encoded", ["secret-not-base64", ""], ids=["invalid", "empty"])
    def test_rejects_invalid_or_empty_data_safely(self, encoded: str) -> None:
        with pytest.raises(ProviderError) as exc_info:
            http.decode_base64_image(
                encoded,
                media_type="image/png",
                provider_name="TestProvider",
            )

        assert exc_info.value.code == ErrorCode.PROVIDER_FAILURE
        assert "secret-not-base64" not in str(exc_info.value)
