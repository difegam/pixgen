"""Test object factories with sensible defaults."""

import itertools
import struct
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


_D50 = (0.9642, 1.0, 0.8249)


def _s15f16(*values: float) -> bytes:
    return b"".join(struct.pack(">i", round(value * 65536)) for value in values)


def _icc_profile(
    *, device_class: bytes, colour_space: bytes, pcs: bytes, tags: dict[bytes, bytes]
) -> bytes:
    """Assemble a minimal ICC v2 profile from a header and tag bodies."""
    description = b"pixgen test profile\0"
    tags = {
        b"desc": b"desc\0\0\0\0"
        + struct.pack(">I", len(description))
        + description
        + bytes(4 + 4 + 2 + 1 + 67),
        b"cprt": b"text\0\0\0\0none\0",
        b"wtpt": b"XYZ \0\0\0\0" + _s15f16(*_D50),
        **tags,
    }
    offset = 128 + 4 + 12 * len(tags)
    table = b""
    data = b""
    for signature, body in tags.items():
        padded = body + bytes(-len(body) % 4)
        table += signature + struct.pack(">II", offset + len(data), len(padded))
        data += padded
    header = (
        struct.pack(">I", offset + len(data))
        + b"lcms"
        + bytes([2, 0x10, 0, 0])
        + device_class
        + colour_space
        + pcs
        + bytes(12)
        + b"acsp"
        + bytes(28)
        + _s15f16(*_D50)
        + bytes(48)
    )
    return header + struct.pack(">I", len(tags)) + table + data


def make_cmyk_output_profile() -> bytes:
    """Return a CMYK printer profile whose ink coverage maps to grey Lab lightness."""
    grid = 2
    lut = bytearray(b"mft1\0\0\0\0" + bytes([4, 3, grid, 0]))
    lut += _s15f16(1, 0, 0, 0, 1, 0, 0, 0, 1)
    lut += bytes(range(256)) * 4
    for cyan, magenta, yellow, black in itertools.product(range(grid), repeat=4):
        ink = min(1.0, (cyan + magenta + yellow) / 3 + black)
        lut += bytes([round(255 * (1 - ink)), 128, 128])
    lut += bytes(range(256)) * 3
    return _icc_profile(
        device_class=b"prtr", colour_space=b"CMYK", pcs=b"Lab ", tags={b"A2B0": bytes(lut)}
    )


def make_grey_profile() -> bytes:
    """Return a linear greyscale display profile."""
    return _icc_profile(
        device_class=b"mntr",
        colour_space=b"GRAY",
        pcs=b"XYZ ",
        tags={b"kTRC": b"curv\0\0\0\0" + struct.pack(">I", 0)},
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
