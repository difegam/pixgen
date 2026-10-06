"""Manage artifact output planning, naming, and atomic writes."""

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.images.mime import MIME_TO_EXTENSION

if TYPE_CHECKING:
    import uuid

__all__: list[str] = [
    "ArtifactWriteResult",
    "OutputPlan",
    "plan_output",
    "save_artifact",
    "write_atomic",
]


@dataclass(frozen=True, slots=True)
class OutputPlan:
    """Planned output path for a single target."""

    model_id: str
    variant: int
    path: Path
    explicit_path: bool = False
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class ArtifactWriteResult:
    """Published artifact path and non-fatal publication warnings."""

    path: Path
    warnings: tuple[str, ...] = ()


def _generate_name(
    model_id: str,
    variant: int,
    media_type: str,
    run_id: uuid.UUID,
    timestamp: str,
) -> str:
    """Generate a unique artifact filename."""
    slug = model_id.replace("/", "-")
    ext = MIME_TO_EXTENSION.get(media_type, "png")
    return f"{timestamp}-{run_id}-{slug}-v{variant}.{ext}"


def _ensure_directory(path: Path, *, mkdir: bool, explicit: bool, label: str) -> None:
    """Validate and create a directory if needed."""

    if path.exists():
        if not path.is_dir():
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"{label} is not a directory: {path}",
            )
        return  # Directory already exists.

    if explicit and not mkdir:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"{label} does not exist: {path} (use --mkdir to create)",
        )

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"cannot create {label}: {path}",
        ) from exc


def _plan_explicit_output(
    path: Path,
    model_id: str,
    *,
    force: bool,
    mkdir: bool,
    declared_media_types: dict[str, str | None] | None,
) -> Path:
    """Validate and prepare an explicit output path."""
    input_media_type = (declared_media_types or {}).get(model_id)
    if input_media_type is not None and not _suffix_matches(path, input_media_type):
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"output suffix {path.suffix!r} conflicts with declared media type {input_media_type}",
        )
    if path.exists() and not force:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"output file already exists: {path} (use --force to overwrite)",
        )
    _ensure_directory(path.parent, mkdir=mkdir, explicit=True, label="output directory")
    return path


def plan_output(
    *,
    model_ids: list[str],
    variants: int,
    output: Path | None = None,
    output_dir: Path | None = None,
    settings_output_dir: Path | None = None,
    mkdir: bool = False,
    force: bool = False,
    run_id: uuid.UUID,
    declared_media_types: dict[str, str | None] | None = None,
) -> list[OutputPlan]:
    """Plan output paths for all targets."""
    total_targets = len(model_ids) * variants
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if output is not None and output_dir is not None:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            "--output and --output-dir are mutually exclusive",
        )

    if output is not None and total_targets > 1:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"--output requires a single target, but {total_targets} targets were specified",
        )

    plans: list[OutputPlan] = []

    for model_id in model_ids:
        for v in range(1, variants + 1):
            if output is not None:
                path = _plan_explicit_output(
                    output,
                    model_id,
                    force=force,
                    mkdir=mkdir,
                    declared_media_types=declared_media_types,
                )
            else:
                base_dir = output_dir or settings_output_dir or Path.cwd() / "pixgen"
                explicit = output_dir is not None or settings_output_dir is not None
                _ensure_directory(
                    base_dir,
                    mkdir=mkdir,
                    explicit=explicit,
                    label="output directory",
                )

                declared = (declared_media_types or {}).get(model_id)
                media_type = declared or "image/png"
                filename = _generate_name(model_id, v, media_type, run_id, timestamp)
                path = base_dir / filename

            plans.append(
                OutputPlan(
                    model_id=model_id,
                    variant=v,
                    path=path,
                    explicit_path=output is not None,
                    overwrite=force if output is not None else False,
                )
            )

    return plans


def _suffix_matches(path: Path, media_type: str) -> bool:
    """Return whether an explicit output suffix matches a media type."""
    suffix = path.suffix.lower().lstrip(".")
    if not suffix:
        return True
    if media_type == "image/jpeg":
        return suffix in {"jpg", "jpeg"}
    return suffix == MIME_TO_EXTENSION.get(media_type)


def _check_extension_mismatch(plan: OutputPlan, media_type: str) -> str | None:
    """Return a warning string if the output suffix doesn't match the media type."""
    if not plan.explicit_path:
        return None
    expected = MIME_TO_EXTENSION.get(media_type)
    actual = plan.path.suffix.lower().lstrip(".")
    if not expected or not actual:
        return None
    accepted = {expected}
    if media_type == "image/jpeg":
        accepted.add("jpeg")
    if actual not in accepted:
        return f"output suffix .{actual} differs from actual media type {media_type}"
    return None


def save_artifact(plan: OutputPlan, data: bytes, media_type: str) -> ArtifactWriteResult:
    """Publish provider bytes according to an output plan."""
    warning = _check_extension_mismatch(plan, media_type)
    warnings = (warning,) if warning else ()
    write_atomic(plan.path, data, overwrite=plan.overwrite)
    return ArtifactWriteResult(path=plan.path, warnings=warnings)


def write_atomic(path: Path, data: bytes, *, overwrite: bool = False) -> None:
    """Write data to a file atomically using a sibling temporary file."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(dir=parent, suffix=".tmp")
    tmp_path = Path(tmp_path_str)

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if overwrite:
            tmp_path.replace(path)
        else:
            try:
                os.link(tmp_path, path)
            except FileExistsError:
                raise
            finally:
                tmp_path.unlink(missing_ok=True)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
