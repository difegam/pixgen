from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_CONFIGURATION = "invalid_configuration"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    MODEL_NOT_FOUND = "model_not_found"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    GENERATION_FAILED = "generation_failed"
    GENERATION_CANCELLED = "generation_cancelled"
    TIMEOUT = "timeout"
    ARTIFACT_ERROR = "artifact_error"
    INTERNAL_ERROR = "internal_error"
