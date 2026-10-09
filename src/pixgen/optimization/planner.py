"""Validate local optimisation requests and preflight destinations without writes."""

import re
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from typing import assert_never

from PIL import Image, UnidentifiedImageError

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.images.inspect import can_encode_format, can_read_format, load_image
from pixgen.images.mime import MIME_TO_EXTENSION
from pixgen.images.models import ImageInputError, LocalImage
from pixgen.images.transform import (
    ImageTransformError,
    ResizeOperation,
    fit_dimensions,
    validate_encoding,
)
from pixgen.optimization.models import (
    OptimizePlan,
    OptimizeRequest,
    OutputFormat,
    PlannedVariant,
    ResizeSpec,
)

__all__: list[str] = ["build_plan"]


def _invalid(message: str) -> PixgenError:
    """Build an invalid-request domain error."""
    return PixgenError(ErrorCode.INVALID_REQUEST, message)


def _dimensions(value: str | int, *, pair: bool) -> tuple[int, int | None]:
    """Parse positive integer dimensions using only the public option grammar."""
    text = str(value)
    pattern = r"[0-9]+x[0-9]+" if pair else r"[0-9]+"
    if re.fullmatch(pattern, text) is None:
        raise _invalid(f"invalid dimensions: {text}")
    try:
        values = tuple(int(part) for part in text.split("x"))
    except ValueError as exc:
        raise _invalid("dimension integer is too large") from exc
    if any(part <= 0 for part in values):
        raise _invalid("dimensions must be positive integers")
    return values[0], values[1] if pair else None


def _specs(request: OptimizeRequest, width: int, height: int) -> tuple[ResizeSpec, ...]:
    """Expand website and custom variants in deterministic option order."""
    if request.width and request.height:
        raise _invalid("width and height options cannot be combined")
    specs: list[ResizeSpec] = []
    if request.web:
        specs.extend(
            (
                ResizeSpec(
                    name="thumbnail", operation=ResizeOperation.COVER, width=400, height=400
                ),
                ResizeSpec(name="card", operation=ResizeOperation.COVER, width=1200, height=630),
                ResizeSpec(name="content", operation=ResizeOperation.WIDTH, width=1280),
                ResizeSpec(name="hero", operation=ResizeOperation.COVER, width=1920, height=1080),
            )
        )
    for operation, values in (
        (ResizeOperation.FIT, request.fit),
        (ResizeOperation.COVER, request.cover),
        (ResizeOperation.WIDTH, request.width),
        (ResizeOperation.HEIGHT, request.height),
    ):
        for value in values:
            first, second = _dimensions(
                value, pair=operation in (ResizeOperation.FIT, ResizeOperation.COVER)
            )
            size = f"{first}x{second}" if second is not None else f"{first}"
            specs.append(
                ResizeSpec(
                    name=f"{operation.lower()}-{size}",
                    operation=operation,
                    width=None if operation is ResizeOperation.HEIGHT else first,
                    height=first if operation is ResizeOperation.HEIGHT else second,
                )
            )
    if not specs:
        specs.append(
            ResizeSpec(name="optimized", operation=ResizeOperation.FIT, width=width, height=height)
        )
    targets = [(spec.operation, spec.width, spec.height) for spec in specs]
    if len(set(targets)) != len(targets):
        raise _invalid("duplicate operation and dimensions")
    return tuple(specs)


def _header_exif(image: Image.Image, content: bytes) -> Image.Exif:
    """Read PNG EXIF chunks without invoking the plugin's pixel-loading getexif."""
    if image.format != "PNG":
        return image.getexif()
    exif = Image.Exif()
    with BytesIO(content) as buffer:
        buffer.seek(8)
        while header := buffer.read(8):
            if len(header) != 8:
                raise _invalid("truncated PNG chunk header")
            length = int.from_bytes(header[:4], "big")
            if header[4:] == b"eXIf":
                exif.load(buffer.read(length))
                return exif
            if header[4:] == b"IEND":
                break
            buffer.seek(length + 4, 1)
    return exif


def _facts(source: LocalImage) -> tuple[str, int, int, bool, str, bytes | None]:
    """Read header facts without loading a source pixel array."""
    try:
        with BytesIO(source.content) as buffer, Image.open(buffer) as image:
            source_format = image.format or ""
            if not can_read_format(source_format):
                raise _invalid(f"decoder unavailable for {source_format}")
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                raise _invalid("animated or multiframe images are unsupported")
            width, height = image.size
            if _header_exif(image, source.content).get(274) in {5, 6, 7, 8}:
                width, height = height, width
            has_alpha = "A" in image.getbands() or "a" in image.getbands()
            transparency = "transparency" in image.info
            mode = "RGBA" if transparency else "RGB" if image.mode == "P" else image.mode
            profile = image.info.get("icc_profile")
            return (
                source_format,
                width,
                height,
                has_alpha or transparency,
                mode,
                profile if isinstance(profile, bytes) else None,
            )
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise _invalid("cannot read source image header") from exc


def _size(spec: ResizeSpec, width: int, height: int) -> tuple[ResizeSpec, int, int, bool]:
    """Calculate effective bounds, dimensions and no-upscale classification."""
    match spec.operation:
        case ResizeOperation.FIT:
            bound_width = min(spec.width or width, width)
            bound_height = min(spec.height or height, height)
            target_width, target_height = fit_dimensions(
                width, height, bounds=(bound_width, bound_height)
            )
            effective = spec.model_copy(update={"width": bound_width, "height": bound_height})
            return effective, target_width, target_height, False
        case ResizeOperation.COVER:
            target_width, target_height = spec.width or width, spec.height or height
            upscale = target_width > width or target_height > height
            return spec, target_width, target_height, upscale
        case ResizeOperation.WIDTH:
            target_width = spec.width or width
            target_height = max(1, round(Fraction(height * target_width, width)))
            return spec, target_width, target_height, target_width > width
        case ResizeOperation.HEIGHT:
            target_height = spec.height or height
            target_width = max(1, round(Fraction(width * target_height, height)))
            return spec, target_width, target_height, target_height > height
        case _:
            assert_never(spec.operation)


def _preflight(path: Path, source: Path, *, force: bool) -> None:
    """Reject source aliases, existing collisions and non-directory parents."""
    if path == source or (path.exists() and path.samefile(source)):
        raise _invalid("output path points to the input source")
    if path.exists() and (not force or not path.is_file()):
        raise _invalid(f"output destination exists: {path}")
    if path.is_symlink():
        raise _invalid(f"output destination is a symbolic link: {path}")
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise _invalid(f"output parent is not a directory: {parent}")


def _encoding(
    request: OptimizeRequest, source_format: str, *, has_alpha: bool
) -> tuple[str, int | None]:
    """Resolve encoding defaults and validate format, quality and transparency."""
    raw_format = request.format
    if raw_format is None:
        raw_format = OutputFormat.WEBP if request.web else OutputFormat.KEEP
    try:
        selected = OutputFormat(raw_format)
    except ValueError as exc:
        raise _invalid(f"invalid output format: {raw_format}") from exc
    output_format = source_format if selected is OutputFormat.KEEP else selected.upper()
    if not can_encode_format(output_format):
        raise _invalid(f"encoder unavailable for {output_format}")
    quality = request.quality if request.quality is not None else (82 if request.web else None)
    if request.quality is not None and not 1 <= request.quality <= 100:
        raise _invalid("quality must be between 1 and 100")
    if output_format == "PNG":
        if request.quality is not None:
            raise _invalid("quality is invalid for PNG output")
        quality = None
    if output_format == "JPEG" and has_alpha:
        raise _invalid("cannot convert transparency to JPEG")
    return output_format, quality


def build_plan(request: OptimizeRequest, *, default_output_dir: Path | None = None) -> OptimizePlan:
    """Inspect source bytes and validate all output decisions without filesystem writes."""
    if request.output is not None and request.output_dir is not None:
        raise _invalid("output and output-dir are mutually exclusive")
    try:
        source = load_image(request.source.resolve())
        source_format, width, height, has_alpha, mode, icc_profile = _facts(source)
        specs = _specs(request, width, height)
        if request.output is not None and len(specs) != 1:
            raise _invalid("output requires exactly one planned result")
        output_format, quality = _encoding(request, source_format, has_alpha=has_alpha)
        validate_encoding(mode, output_format=output_format, icc_profile=icc_profile)
        extension = MIME_TO_EXTENSION[f"image/{output_format.lower()}"]
        directory = (request.output_dir or default_output_dir or Path.cwd() / "pixgen").resolve()
        variants: list[PlannedVariant] = []
        destinations: set[Path] = set()
        for spec in specs:
            named_output = directory / f"{source.source_path.stem}-{spec.name}.{extension}"
            candidate = request.output or named_output
            if request.output is not None:
                if candidate.is_dir():
                    raise _invalid(f"output destination is a directory: {candidate}")
                candidate = candidate.with_suffix(f".{extension}")
            if candidate.is_symlink():
                raise _invalid(f"output destination is a symbolic link: {candidate}")
            destination = candidate.resolve()
            if destination in destinations:
                raise _invalid("duplicate output destinations")
            destinations.add(destination)
            _preflight(destination, source.source_path, force=request.force)
            effective, target_width, target_height, upscale = _size(spec, width, height)
            variants.append(
                PlannedVariant(
                    spec=effective,
                    output_path=destination,
                    width=target_width,
                    height=target_height,
                    reason="would upscale" if upscale else None,
                )
            )
        return OptimizePlan(
            request=request,
            source=source,
            source_format=source_format,
            source_width=width,
            source_height=height,
            has_alpha=has_alpha,
            format=output_format,
            quality=quality,
            variants=tuple(variants),
        )
    except (ImageInputError, ImageTransformError) as exc:
        raise _invalid(exc.reason) from exc
    except OSError as exc:
        raise _invalid("cannot resolve or inspect output paths") from exc
