"""Cross-cutting helpers shared between provider CLI modules."""

from pydantic import TypeAdapter, ValidationError

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.core.models import ModelId

__all__: list[str] = ["normalize_model_id"]


def normalize_model_id(
    value: str,
    *,
    prefix: str,
    error_message: str,
    allow_nested: bool = False,
) -> str:
    """Validate and canonicalise a provider-local model name."""
    if not allow_nested:
        if value.startswith(f"{prefix}/"):
            return value
        if "/" in value:
            raise PixgenError(ErrorCode.INVALID_REQUEST, error_message)
        return f"{prefix}/{value}"

    model_id = value if value.startswith(f"{prefix}/") else f"{prefix}/{value}"
    try:
        return TypeAdapter(ModelId).validate_python(model_id)
    except ValidationError as exc:
        raise PixgenError(ErrorCode.INVALID_REQUEST, error_message) from exc
