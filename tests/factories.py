"""Test object factories with sensible defaults."""

from __future__ import annotations

from datetime import date

from pixgen.core.models import (
    ImageOperation,
    MediaRole,
    MediaRoleSpec,
    ModelId,
    ModelSpec,
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
