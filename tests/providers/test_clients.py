"""Tests for providers.clients."""

import httpx2
import pytest

from pixgen.core.errors import ErrorCode, ProviderError
from pixgen.providers.clients import LazyClient
from pixgen.providers.openai import OpenAIProvider
from pixgen.providers.openrouter import OpenRouterProvider


class FakeClient:
    """Client that records whether it was closed."""

    def __init__(self) -> None:
        self.closed = False


async def _close(client: FakeClient) -> None:
    client.closed = True


class TestLazyClient:
    def test_builds_client_once(self) -> None:
        holder = LazyClient(None, FakeClient, close=_close, label="Fake")

        assert holder.get() is holder.get()

    async def test_closes_built_client_and_builds_a_fresh_one(self) -> None:
        holder = LazyClient(None, FakeClient, close=_close, label="Fake")
        first = holder.get()

        await holder.aclose()
        await holder.aclose()

        assert first.closed
        assert holder.get() is not first

    async def test_leaves_injected_client_open(self) -> None:
        injected = FakeClient()
        holder = LazyClient(injected, FakeClient, close=_close, label="Fake")

        await holder.aclose()

        assert not injected.closed
        assert holder.get() is injected

    @pytest.mark.parametrize(
        ("client", "factory", "expected"),
        [(None, None, False), (FakeClient(), None, True), (None, FakeClient, True)],
        ids=["neither", "injected", "factory"],
    )
    def test_available(self, client, factory, expected) -> None:
        holder = LazyClient(client, factory, close=_close, label="Fake")

        assert holder.available is expected

    def test_raises_without_client_or_factory(self) -> None:
        holder = LazyClient[FakeClient](None, None, close=_close, label="Fake")

        with pytest.raises(ProviderError) as exc_info:
            holder.get()

        assert exc_info.value.code == ErrorCode.CREDENTIAL_UNAVAILABLE
        assert exc_info.value.message == "Fake API key not configured"


@pytest.mark.parametrize(
    "provider_cls", [OpenAIProvider, OpenRouterProvider], ids=["openai", "openrouter"]
)
async def test_http_providers_close_the_client_they_built(
    provider_cls: type[OpenAIProvider | OpenRouterProvider],
) -> None:
    client = httpx2.AsyncClient()
    provider = provider_cls(None, client_factory=lambda: client)
    provider._client.get()

    await provider.aclose()

    assert client.is_closed
