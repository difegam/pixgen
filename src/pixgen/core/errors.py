from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import ValidationError
__all__: list[str] = [
    "ErrorCode",
    "PixgenError",
    "ProviderError",
    "validation_message",
]


class ErrorCode(StrEnum):
    """Public error codes for CLI and JSON output."""

    INVALID_REQUEST = "invalid_request"
    INVALID_CONFIGURATION = "invalid_configuration"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    MODEL_NOT_FOUND = "model_not_found"
    CONTENT_REJECTED = "content_rejected"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"
    PROVIDER_FAILURE = "provider_failure"
    ARTIFACT_FAILURE = "artifact_failure"


class PixgenError(Exception):
    """Base exception for all Pixgen domain errors."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code.value}: {message}")


class ProviderError(PixgenError):
    """Raised when a provider operation fails."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(code, message)


def validation_message(error: ValidationError) -> str:
    """Return a safe, concise message for expected model validation failures."""
    details: list[str] = []
    for item in error.errors(include_context=False, include_input=False, include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "value"
        details.append(f"{location}: {item['type']}")
    return "invalid value" if not details else "invalid parameters: " + "; ".join(details)
