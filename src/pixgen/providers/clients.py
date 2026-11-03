"""Hold a provider's client, creating it lazily and closing only what it created."""

from typing import TYPE_CHECKING

from pixgen.core.errors import ErrorCode, ProviderError

__all__: list[str] = [
    "LazyClient",
]

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class LazyClient[ClientT]:
    """Hand out a provider client, building it from a factory on first use.

    An injected client belongs to the caller, so ``aclose`` leaves it open. A client
    built from the factory belongs to this holder: ``aclose`` closes it and the next
    ``get`` builds a fresh one.
    """

    def __init__(
        self,
        client: ClientT | None,
        factory: Callable[[], ClientT] | None,
        *,
        close: Callable[[ClientT], Awaitable[None]],
        label: str,
    ) -> None:
        self._injected = client
        self._factory = factory
        self._close = close
        self._label = label
        self._created: ClientT | None = None

    @property
    def available(self) -> bool:
        """Report whether a client is injected or can be built."""
        return self._injected is not None or self._factory is not None

    def get(self) -> ClientT:
        """Return the injected client, or the factory-built one, building it if needed.

        Raises:
            ProviderError: If there is neither an injected client nor a factory.
        """
        if self._injected is not None:
            return self._injected
        if self._created is None:
            if self._factory is None:
                raise ProviderError(
                    ErrorCode.CREDENTIAL_UNAVAILABLE, f"{self._label} API key not configured"
                )
            self._created = self._factory()
        return self._created

    async def aclose(self) -> None:
        """Close the factory-built client, if any. Safe to call repeatedly."""
        client = self._created
        if client is None:
            return
        self._created = None
        await self._close(client)
