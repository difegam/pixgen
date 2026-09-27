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
    provider, model = model_id.split("/", 1)
    ext = MIME_TO_EXTENSION.get(media_type, "png")
    return f"{timestamp}-{run_id}-{provider}-{model}-v{variant}.{ext}"


def plan_output(  # noqa: C901
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
                path = output
                declared = (declared_media_types or {}).get(model_id)
                if declared is not None and not _suffix_matches(path, declared):
                    raise PixgenError(
                        ErrorCode.INVALID_REQUEST,
                        "output suffix "
                        f"{path.suffix!r} conflicts with declared media type {declared}",
                    )
                if path.exists() and not force:
                    raise PixgenError(
                        ErrorCode.INVALID_REQUEST,
                        f"output file already exists: {path} (use --force to overwrite)",
                    )
                parent = path.parent
                if not parent.exists():
                    if not mkdir:
                        raise PixgenError(
                            ErrorCode.INVALID_REQUEST,
                            f"output directory does not exist: {parent} (use --mkdir to create)",
                        )
                    try:
                        parent.mkdir(parents=True, exist_ok=True)
                    except OSError as exc:
                        raise PixgenError(
                            ErrorCode.INVALID_REQUEST,
                            f"cannot create output directory: {parent}",
                        ) from exc
                elif not parent.is_dir():
                    raise PixgenError(
                        ErrorCode.INVALID_REQUEST,
                        f"output parent is not a directory: {parent}",
                    )
            else:
                base_dir = output_dir or settings_output_dir or Path.cwd() / "pixgen"
                if not base_dir.exists():
                    if (output_dir is not None or settings_output_dir is not None) and not mkdir:
                        raise PixgenError(
                            ErrorCode.INVALID_REQUEST,
                            f"output directory does not exist: {base_dir} (use --mkdir to create)",
                        )
                    try:
                        base_dir.mkdir(parents=True, exist_ok=True)
                    except OSError as exc:
                        raise PixgenError(
                            ErrorCode.INVALID_REQUEST,
                            f"cannot create output directory: {base_dir}",
                        ) from exc
                elif not base_dir.is_dir():
                    raise PixgenError(
                        ErrorCode.INVALID_REQUEST,
                        f"output directory is not a directory: {base_dir}",
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


def save_artifact(plan: OutputPlan, data: bytes, media_type: str) -> ArtifactWriteResult:
    """Publish provider bytes according to an output plan."""
    warnings: tuple[str, ...] = ()
    expected_extension = MIME_TO_EXTENSION.get(media_type)
    actual_extension = plan.path.suffix.lower().lstrip(".")
    if plan.explicit_path and expected_extension and actual_extension:
        accepted_extensions = {expected_extension}
        if media_type == "image/jpeg":
            accepted_extensions.add("jpeg")
        if actual_extension not in accepted_extensions:
            warnings = (
                f"output suffix .{actual_extension} differs from actual media type {media_type}",
            )
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
