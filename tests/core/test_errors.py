"""Tests for core.errors."""

import pytest

from pixgen.core.errors import ErrorCode, PixgenError, ProviderError


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_all_codes_present(self) -> None:
        expected = {
            "INVALID_REQUEST",
            "INVALID_CONFIGURATION",
            "CREDENTIAL_UNAVAILABLE",
            "AUTHENTICATION_FAILED",
            "RATE_LIMITED",
            "MODEL_NOT_FOUND",
            "CONTENT_REJECTED",
            "PROVIDER_UNAVAILABLE",
            "TIMEOUT",
            "INTERRUPTED",
            "PROVIDER_FAILURE",
            "ARTIFACT_FAILURE",
        }
        actual = {member.name for member in ErrorCode}
        assert actual == expected

    def test_values_are_snake_case(self) -> None:
        assert ErrorCode.INVALID_REQUEST == "invalid_request"
        assert ErrorCode.CONTENT_REJECTED == "content_rejected"
        assert ErrorCode.PROVIDER_FAILURE == "provider_failure"


class TestPixgenError:
    """Tests for PixgenError base exception."""

    def test_is_exception(self) -> None:
        assert issubclass(PixgenError, Exception)


class TestProviderError:
    """Tests for ProviderError."""

    def test_captures_code_and_message(self) -> None:
        error = ProviderError(ErrorCode.TIMEOUT, "request timed out")
        assert error.code == ErrorCode.TIMEOUT
        assert error.message == "request timed out"
        assert "timeout: request timed out" in str(error)

    def test_inherits_from_pixgen_error(self) -> None:
        error = ProviderError(ErrorCode.PROVIDER_FAILURE, "failed")
        assert isinstance(error, PixgenError)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(ProviderError) as exc_info:
            raise ProviderError(ErrorCode.RATE_LIMITED, "too many requests")
        assert exc_info.value.code == ErrorCode.RATE_LIMITED
