"""Validate local optimisation requests and preflight destinations without writes."""

import re
from typing import TYPE_CHECKING

from pixgen.artifacts import check_directory, default_output_directory, suffix_matches
from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.images.inspect import has_codec, inspect_header, load_image
from pixgen.images.models import ImageFacts, ImageFormat, ImageInputError
from pixgen.images.transform import ImageTransformError, ResizeOperation, check_colour_profile
from pixgen.optimization.models import (
    OptimizePlan,
    OptimizeRequest,
    OutputFormat,
    PlannedVariant,
    ResizeSpec,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = ["build_plan"]

_WEB_QUALITY = 82

_WEB_PRESET: tuple[ResizeSpec, ...] = (
    ResizeSpec(name="thumbnail", operation=ResizeOperation.COVER, width=400, height=400),
    ResizeSpec(name="card", operation=ResizeOperation.COVER, width=1200, height=630),
    ResizeSpec(name="content", operation=ResizeOperation.WIDTH, width=1280),
    ResizeSpec(name="hero", operation=ResizeOperation.COVER, width=1920, height=1080),
)


def _invalid_request(message: str) -> PixgenError:
    """Build an invalid-request domain error."""
    return PixgenError(ErrorCode.INVALID_REQUEST, message)


def _parse_size(value: str | int, operation: ResizeOperation) -> ResizeSpec:
    """Parse one sizing option value into a named spec using the public option grammar."""
    text = str(value)
    pair = operation.takes_width and operation.takes_height
    if re.fullmatch(r"[0-9]+x[0-9]+" if pair else r"[0-9]+", text) is None:
        raise _invalid_request(f"invalid dimensions: {text}")
    try:
        values = [int(part) for part in text.split("x")]
    except ValueError as exc:
        raise _invalid_request("dimension integer is too large") from exc
    if any(part <= 0 for part in values):
        raise _invalid_request("dimensions must be positive integers")
    size = "x".join(str(part) for part in values)
    return ResizeSpec(
        name=f"{operation}-{size}",
        operation=operation,
        width=values[0] if operation.takes_width else None,
        height=values[-1] if operation.takes_height else None,
    )


def _resize_specs(request: OptimizeRequest, facts: ImageFacts) -> tuple[ResizeSpec, ...]:
    """Expand website and custom variants in deterministic option order."""
    if request.width and request.height:
        raise _invalid_request("width and height options cannot be combined")
    specs = list(_WEB_PRESET) if request.web else []
    for operation, values in (
        (ResizeOperation.FIT, request.fit),
        (ResizeOperation.COVER, request.cover),
        (ResizeOperation.WIDTH, request.width),
        (ResizeOperation.HEIGHT, request.height),
    ):
        specs.extend(_parse_size(value, operation) for value in values)
    if not specs:
        specs.append(
            ResizeSpec(
                name="optimized",
                operation=ResizeOperation.FIT,
                width=facts.width,
                height=facts.height,
            )
        )
    targets = [(spec.operation, spec.width, spec.height) for spec in specs]
    if len(set(targets)) != len(targets):
        raise _invalid_request("duplicate operation and dimensions")
    return tuple(specs)


def _resolve_encoding(
    request: OptimizeRequest, facts: ImageFacts
) -> tuple[ImageFormat, int | None]:
    """Resolve the output encoding and quality, and validate quality and transparency."""
    selected = request.format or (OutputFormat.WEBP if request.web else OutputFormat.KEEP)
    output_format = selected.resolve(facts.format)
    if not has_codec(output_format, encode=True):
        raise _invalid_request(f"encoder unavailable for {output_format.pillow_name}")
    if request.quality is not None and not 1 <= request.quality <= 100:
        raise _invalid_request("quality must be between 1 and 100")
    quality = (
        request.quality if request.quality is not None else (_WEB_QUALITY if request.web else None)
    )
    if output_format is ImageFormat.PNG:
        if request.quality is not None:
            raise _invalid_request("quality is invalid for PNG output")
        quality = None
    if output_format is ImageFormat.JPEG and facts.has_alpha:
        raise _invalid_request("cannot convert transparency to JPEG")
    return output_format, quality


def _explicit_output_path(output: Path, output_format: ImageFormat) -> Path:
    """Add the format's extension to a bare name, or reject a conflicting one."""
    if output.is_dir():
        raise _invalid_request(f"output destination is a directory: {output}")
    if not output.suffix:
        return output.with_suffix(f".{output_format.extension}")
    if not suffix_matches(output, output_format.media_type):
        raise _invalid_request(
            f"output suffix {output.suffix!r} conflicts with {output_format.pillow_name} output"
        )
    return output


def _check_destination(path: Path, source: Path, *, force: bool) -> None:
    """Reject source aliases, existing collisions, symlinks and non-directory parents."""
    if path == source or (path.exists() and path.samefile(source)):
        raise _invalid_request("output path points to the input source")
    if path.is_symlink():
        raise _invalid_request(f"output destination is a symbolic link: {path}")
    if path.exists() and (not force or not path.is_file()):
        raise _invalid_request(f"output destination exists: {path}")
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise _invalid_request(f"output parent is not a directory: {parent}")


def _plan_variants(
    request: OptimizeRequest,
    source: Path,
    facts: ImageFacts,
    output_format: ImageFormat,
    *,
    directory: Path,
    explicit_directory: bool,
) -> tuple[PlannedVariant, ...]:
    """Resolve each variant's size and destination, preflighting only those that run."""
    variants: list[PlannedVariant] = []
    destinations: set[Path] = set()
    for spec in _resize_specs(request, facts):
        if request.output is not None:
            candidate = _explicit_output_path(request.output, output_format)
        else:
            candidate = directory / f"{source.stem}-{spec.name}.{output_format.extension}"
        target = spec.resolve(facts.width, facts.height)
        if target is None:
            variants.append(
                PlannedVariant(spec=spec, output_path=candidate.absolute(), target=None)
            )
            continue
        if candidate.is_symlink():
            raise _invalid_request(f"output destination is a symbolic link: {candidate}")
        destination = candidate.resolve()
        if destination in destinations:
            raise _invalid_request("duplicate output destinations")
        destinations.add(destination)
        _check_destination(destination, source, force=request.force)
        check_directory(
            destination.parent,
            mkdir=request.mkdir,
            explicit=explicit_directory,
            label="output directory",
        )
        variants.append(PlannedVariant(spec=spec, output_path=destination, target=target))
    if request.output is not None and len(variants) != 1:
        raise _invalid_request("output requires exactly one planned result")
    return tuple(variants)


def build_plan(request: OptimizeRequest, *, default_output_dir: Path | None = None) -> OptimizePlan:
    """Inspect the source header and validate all output decisions without filesystem writes.

    Args:
        request: The optimisation options.
        default_output_dir: Configured output directory, used when the request names none.

    Returns:
        The validated plan with every variant in request order.

    Raises:
        PixgenError: With ``invalid_request`` for any invalid option, source or destination.
    """
    if request.output is not None and request.output_dir is not None:
        raise _invalid_request("output and output-dir are mutually exclusive")
    try:
        source = load_image(request.source.resolve(), verify=False)
        facts = inspect_header(source)
        if not has_codec(facts.format, encode=False):
            raise _invalid_request(f"decoder unavailable for {facts.format.pillow_name}")
        output_format, quality = _resolve_encoding(request, facts)
        check_colour_profile(facts, output_format=output_format)
        variants = _plan_variants(
            request,
            source.source_path,
            facts,
            output_format,
            directory=request.output_dir or default_output_dir or default_output_directory(),
            explicit_directory=any(
                value is not None
                for value in (request.output, request.output_dir, default_output_dir)
            ),
        )
        return OptimizePlan(
            request=request,
            source=source,
            format=output_format,
            quality=quality,
            variants=variants,
        )
    except (ImageInputError, ImageTransformError) as exc:
        raise _invalid_request(exc.reason) from exc
    except OSError as exc:
        raise _invalid_request("cannot resolve or inspect output paths") from exc
