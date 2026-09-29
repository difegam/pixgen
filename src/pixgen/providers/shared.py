"""Cross-cutting helpers shared between provider CLI modules."""

from pixgen.core.errors import ErrorCode, PixgenError

__all__: list[str] = ["normalize_model_id"]


def normalize_model_id(value: str, *, prefix: str, error_message: str) -> str:
    """Validate and canonicalise a provider-local model name."""
    if value.startswith(f"{prefix}/"):
        return value
    if "/" in value:
        raise PixgenError(ErrorCode.INVALID_REQUEST, error_message)
    return f"{prefix}/{value}"
