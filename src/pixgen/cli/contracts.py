"""Define provider-owned CLI factory contracts."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cyclopts import App

    from pixgen.cli.invoke import CommandInvoker
    from pixgen.core.models import ImageOperation

__all__: list[str] = ["ProviderCliFactory"]


@runtime_checkable
class ProviderCliFactory(Protocol):
    """Build a provider sub-app for one image operation."""

    name: str
    operations: frozenset[ImageOperation]

    def build(self, operation: ImageOperation, invoker: CommandInvoker) -> App:
        """Return the provider-owned app for an operation."""
        ...
