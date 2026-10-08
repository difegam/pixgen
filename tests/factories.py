"""Test object factories with sensible defaults."""

from base64 import b64decode
from datetime import date

from pixgen.core.definitions import ModelDefinition
from pixgen.core.models import (
    ImageOperation,
    JsonObject,
    MediaRole,
    MediaRoleSpec,
    ModelId,
    ModelSpec,
)
from pixgen.core.parameters import ProviderParams


def make_cmyk_profile() -> bytes:
    """Return a LittleCMS-generated linear CMYK device-link profile."""
    return b64decode(
        "AAACKGxjbXMEQAAAbGlua0NNWUtDTVlLB+oACgAIABQAMwAGYWNzcEFQUEwAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1sY21zAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAFZGVzYwAAAMAAAABIY3BydAAAAQgAAABMQTJCMAAAAVQAAABgcHNl"
        "cQAAAbQAAABAcHNpZAAAAfQAAAA0bWx1YwAAAAAAAAABAAAADGVuVVMAAAAsAAAAHABMAGkAbgBl"
        "AGEAcgBpAHoAYQB0AGkAbwBuACAAYgB1AGkAbAB0AC0AaQBubWx1YwAAAAAAAAABAAAADGVuVVMA"
        "AAAwAAAAHABOAG8AIABjAG8AcAB5AHIAaQBnAGgAdAAsACAAdQBzAGUAIABmAHIAZQBlAGwAeW1B"
        "QiAAAAAABAQAAAAAACAAAAAAAAAAAAAAAAAAAAAAcGFyYQAAAAAAAAAAAAEAAHBhcmEAAAAAAAAAAAAB"
        "AABwYXJhAAAAAAAAAAAAAQAAcGFyYQAAAAAAAAAAAAEAAHBzZXEAAAAAAAAAAQAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAbWx1YwAAAAAAAAAAAAAADG1sdWMAAAAAAAAAAAAAAAxwc2lkAAAAAAAAAAEAAAAUAAAAIAAA"
        "AAAAAAAAAAAAAAAAAABtbHVjAAAAAAAAAAAAAAAM"
    )


def make_media_role_spec(
    *,
    minimum: int = 0,
    maximum: int = 1,
    formats: frozenset[str] = frozenset({"png", "jpeg", "webp"}),
    max_bytes: int | None = None,
) -> MediaRoleSpec:
    """Create a MediaRoleSpec with test-friendly defaults."""
    return MediaRoleSpec(minimum=minimum, maximum=maximum, formats=formats, max_bytes=max_bytes)


def make_model_spec(
    *,
    model_id: ModelId = "openai/gpt-image-2",
    display_name: str = "GPT Image 2",
    operations: frozenset[ImageOperation] = frozenset(
        {ImageOperation.IMAGE_CREATE, ImageOperation.IMAGE_EDIT}
    ),
    media: dict[MediaRole, MediaRoleSpec] | None = None,
    documentation_url: str = "https://platform.openai.com/docs",
    verified_at: date = date(2026, 9, 24),
) -> ModelSpec:
    """Create a ModelSpec with realistic defaults."""
    if media is None:
        media = {
            MediaRole.REFERENCE: make_media_role_spec(minimum=0, maximum=16),
            MediaRole.IMAGE: make_media_role_spec(minimum=1, maximum=16),
        }
    return ModelSpec(
        id=model_id,
        display_name=display_name,
        operations=operations,
        media=media,
        documentation_url=documentation_url,
        verified_at=verified_at,
    )


def make_model_definition[P: ProviderParams](
    *,
    spec: ModelSpec | None = None,
    parameter_type: type[P] = ProviderParams,
    aspect_ratios: dict[str, JsonObject] | None = None,
) -> ModelDefinition[P]:
    """Create a ModelDefinition with default native parameters."""
    return ModelDefinition[parameter_type](
        spec=spec if spec is not None else make_model_spec(),
        parameter_type=parameter_type,
        defaults=parameter_type(),
        aspect_ratios=aspect_ratios or {},
    )
