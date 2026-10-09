# Website Image Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Revision note (2026-09-30):** This plan was rewritten against the current `main` branch, which already ships a working CLI (`pixgen create`/`pixgen edit`/`pixgen model`), error contract, output rendering, and atomic artifact writer. The original 2026-09-19 draft assumed those did not exist yet and invented its own error schema, exit-code table, and Tinify credential store. This revision reuses the real modules instead of duplicating them. See "What changed since the original draft" below.

**Goal:** Add a standalone `pixgen optimize` command that creates website-ready image variants locally with Pillow, or explicitly through Tinify, from a local source image.

**Architecture:** A pure planner inspects and validates the source, expands presets, applies no-upscale rules, and resolves destinations before any network access. A private batch `Optimizer` protocol supports a sequential Pillow implementation and a bounded-concurrency Tinify implementation; a runner owns staged files, artifact validation, and promotion through the existing `pixgen.artifacts.write_atomic`, plus ordered partial results. The feature adds only the `optimization/` subsystem and the CLI/result/error extensions it needs; it does not implement image generation (already shipped) or any database persistence.

**Tech Stack:** Python 3.14, Cyclopts 4, Pydantic 2, Pillow (already a dependency) plus `pillow-avif-plugin` for AVIF, HTTPX2 (already a dependency), Rich, pytest, Ruff, Pyrefly, prek.

**Spec:** `docs/superpowers/specs/2026-09-19-image-optimization-design.md` — re-read it alongside this plan; several of its module names have also drifted (it predates `core/results.py`, `cli/outcome.py`, and the current `artifacts.py`). Treat this plan's module names as authoritative where they conflict.

### What changed since the original draft

- **CLI shape:** commands mount at CLI root (`pixgen create`, `pixgen edit`, `pixgen model`) — there is no `image` subgroup. `pixgen image optimize` becomes root-level **`pixgen optimize SOURCE ...`**.
- **Error/result contract:** the app already has `pixgen.core.errors.ErrorCode` + `PixgenError`, `pixgen.core.results.PublicError`/`CommandResult`/`TargetResult`, and `pixgen.cli.outcome.CliOutcome`/`ExitStatus`/`render_outcome`. This plan extends those instead of inventing `ErrorDetail`/`ErrorEnvelope` and a bespoke 0–7 exit table.
- **Exit codes:** reuse `ExitStatus` (`SUCCESS=0`, `REJECTED=2`, `ALL_FAILED=3`, `PARTIAL_FAILURE=4`; `1` is left to Cyclopts parse errors). There is no dedicated code for "some variants skipped by design" — a no-upscale skip is an expected planning outcome, not a failure, so a run with skips but no engine failures is `SUCCESS`. A run with at least one engine `FAILED` variant and at least one `COMPLETED` variant is `PARTIAL_FAILURE`; all variants `FAILED` is `ALL_FAILED`.
- **Atomic writes:** reuse `pixgen.artifacts.write_atomic(path, data, overwrite=...)` for final promotion instead of a bespoke fsync/`os.replace` routine. Collision/force checks happen once, during planning (matching how `artifacts.plan_output` already works for `create`/`edit`).
- **Dependencies:** `pillow>=12.3.0` and `httpx2>=2.12.0` are already in `pyproject.toml` — nothing to add there. AVIF is **not** bundled in Pillow's PyPI wheels (confirmed via research); it needs the separate `pillow-avif-plugin` package plus `import pillow_avif` before any AVIF read/write, or AVIF support silently fails.
- **No SQLite, no `sqlmodel`, no `stamina`:** the original Task 1 added both as dependencies even though the plan's own constraints forbid persisting optimization runs. Dropped entirely — nothing in the repo uses them.
- **No OS keyring:** `README.md` lists "OS-keyring credentials" as explicitly deferred, and `AGENTS.md` documents provider keys as env-var-only (`OPENAI_API_KEY`, `GEMINI_API_KEY`). Tinify credentials follow the same pattern: a `tinify_api_key: SecretStr | None` field on the existing `Settings` model, resolved from `TINIFY_API_KEY`/`PIXGEN_TINIFY_API_KEY`. No `CredentialResolver`, no keyring backend, no `credentials.py`.
- **Coordination with `docs/superpowers/plans/2026-09-27-media-commands.md`:** that plan's architecture line says it will "reuse ... the planned local optimization engine for codec operations," but its own tasks build an independent `media/transform.py` with no import from `optimization/local.py`. This plan does not resolve that seam (out of scope — it belongs to whichever plan lands second), but Task 5 below flags the exact primitives (`_load_source`, `_encode_variant`) that a future refactor could lift into a shared `pixgen/images/` module so `media/transform.py` and `optimization/local.py` stop duplicating EXIF-normalize/encode logic.

## Global Constraints

- Do not add `sqlmodel`, `stamina`, or `keyring` as dependencies. Add `pillow-avif-plugin` and register it (`import pillow_avif`) before any AVIF encode/decode.
- The only entry point is the standalone `pixgen optimize` command; generated images are never optimized implicitly.
- `local` is the default, offline engine. `tinify` is selected explicitly via `--engine tinify` and is the only action that authorizes source upload and possible API charges.
- Support only static PNG, JPEG, WebP, and AVIF; reject animated images, SVG, video, and transparent-to-JPEG conversion.
- Never upscale. Keep valid completed variants when another variant is skipped or fails.
- Normalize EXIF orientation, strip EXIF/XMP/GPS, and retain ICC locally where the encoder supports it; Tinify output does not promise ICC retention.
- Never overwrite without `--force`, never create missing parents without `--mkdir`. Collision/force/parent checks happen during planning, before any credential lookup or network access; final promotion reuses `pixgen.artifacts.write_atomic`.
- `--dry-run` performs no credential lookup, network request, file write, or directory creation.
- Do not persist optimization runs anywhere; do not add a public optimizer plugin API.
- Never retry `POST /shrink` or Tinify derivative `POST` requests. Retry only safe `GET` downloads, with a bound, jitter, and `Retry-After` support.
- Validate Tinify output URLs as exact HTTPS `api.tinify.com/output/<token>` URLs before following them; never expose credentials, authorization headers, provider bodies, or output URLs.
- `OptimizeResult.schema_version` is the string `"1"` (matching `CommandResult`/`ModelListResult`), variant order is plan order, and exit codes reuse the existing `ExitStatus`: `0` success (including skip-only runs), `2` rejected (usage/validation/configuration/credential, mirroring `PixgenError` → `command_error`), `3` all variants failed, `4` some variants failed. Cyclopts owns `1` for its own parse errors.

## Review Focus

- A JPEG whose EXIF orientation swaps width and height must be planned against normalized dimensions; Tinify must upload one normalized, metadata-free intermediate and clean it up.
- A transparent source requested as JPEG must fail before credential lookup, directory creation, or network access.
- A malicious Tinify `Location` such as another host, user-info URL, query-bearing URL, or deceptive `/output/../` path must be rejected without a follow-up request.
- A failed promotion must leave the old destination byte-for-byte intact (verify `write_atomic`'s existing no-clobber/replace behaviour is exercised correctly, not reinvented), remove temporary stage files, and preserve already-promoted sibling variants.
- Concurrent Tinify responses that complete out of order, including one derivative failure, must still return planned order, retain successes, sanitize the failure, and map to `ExitStatus.PARTIAL_FAILURE`.

---

## File Map

### Shared foundation (extend, do not recreate)

- Modify `pyproject.toml`: add `pillow-avif-plugin`, add the `live_tinify` pytest marker. Do **not** add `sqlmodel`, `stamina`, or `keyring`.
- Modify `uv.lock` via `uv lock`.
- Modify `.gitignore` to ignore `.superpowers/` visual-companion state, if not already present.
- Modify `src/pixgen/core/errors.py` to add `ErrorCode.OPTIMIZATION_FAILED`.
- Modify `src/pixgen/core/results.py` to add `VariantStatus`, `OptimizeVariantResult`, `OptimizeResult`.
- Modify `src/pixgen/cli/outcome.py` to extend the `PublicResult` union, `exit_status`, and `render_outcome` for `OptimizeResult`.
- Modify `src/pixgen/cli/render.py` to add `render_optimize_result`.
- Modify `src/pixgen/images/mime.py` to add `"image/avif": "avif"`.
- Modify `src/pixgen/config/models.py` to add `Settings.tinify_api_key: SecretStr | None`, matching the existing `openai_api_key`/`gemini_api_key` fields.

### Optimization subsystem (new)

- Create `src/pixgen/optimization/__init__.py` for the private package surface.
- Create `src/pixgen/optimization/models.py` for the request, source-facts, plan, and engine-output types that are internal to planning/execution (not part of the public result contract, which lives in `core/results.py`).
- Create `src/pixgen/optimization/planner.py` for variant parsing, `--web` merging, source inspection, capability checks, cost bounds, and destinations.
- Create `src/pixgen/optimization/base.py` for the private batch `Optimizer` protocol.
- Create `src/pixgen/optimization/local.py` for one-decode Pillow transformations.
- Create `src/pixgen/optimization/tinify.py` for direct HTTPX2 upload, transformations, safe reads, and error translation.
- Create `src/pixgen/optimization/runner.py` for staging, validation, promotion (via `artifacts.write_atomic`), cleanup, and partial aggregation.
- Create `src/pixgen/cli/optimize.py` for the `pixgen optimize` command, following the pattern in `src/pixgen/cli/image.py`.
- Modify `src/pixgen/cli/app.py` to register the optimize command alongside `create`/`edit`/`model`.

### Diagnostics (new)

- Create `src/pixgen/cli/system.py` for `pixgen info` and `pixgen doctor`.

### Tests, docs, and agent guidance

- Create focused tests under `tests/optimization/`, `tests/providers/`, `tests/cli/`, `tests/integration/`, and `tests/live/`, mirroring the existing `tests/` layout (`tests/application/`, `tests/cli/`, `tests/providers/`, `tests/images/`).
- Extend `tests/conftest.py`/`tests/factories.py` with deterministic static, animated, transparent, and oriented image fixtures.
- Create `docs/image-optimization.md` and update `README.md`.
- Create `skills/pixgen/SKILL.md` and `skills/pixgen/references/image-optimization.md` if a Pixgen agent skill does not already exist; otherwise extend it.

---

### Task 1: Wire the Optimize Result, Error, and Exit Contracts

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/pixgen/core/errors.py`
- Modify: `src/pixgen/core/results.py`
- Modify: `src/pixgen/cli/outcome.py`
- Modify: `src/pixgen/cli/render.py`
- Modify: `src/pixgen/images/mime.py`
- Test: `tests/core/test_errors.py`
- Test: `tests/core/test_results.py`
- Test: `tests/cli/test_outcome.py`

**Interfaces:**
- Consumes: existing `ErrorCode`, `PixgenError`, `PublicError`, `CliOutcome`, `ExitStatus`, `render_outcome`.
- Produces: `ErrorCode.OPTIMIZATION_FAILED`, `VariantStatus`, `OptimizeVariantResult`, `OptimizeResult`, extended `PublicResult` union, extended `exit_status`, `render_optimize_result`, `MIME_TO_EXTENSION["image/avif"]`.

- [ ] **Step 1: Write failing tests for the extended contracts**

```python
from pixgen.core.errors import ErrorCode
from pixgen.core.results import OptimizeResult, OptimizeVariantResult, VariantStatus


def test_optimization_failed_error_code_exists() -> None:
    assert ErrorCode.OPTIMIZATION_FAILED == "optimization_failed"


def test_optimize_result_requires_variants_or_error() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OptimizeResult(
            run_id=__import__("uuid").uuid4(),
            engine="local",
            source=__import__("pathlib").Path("a.jpg"),
            source_bytes=1,
        )
```

Add a `cli/test_outcome.py` case asserting `exit_status` returns `ExitStatus.SUCCESS` for an `OptimizeResult` whose variants are all `COMPLETED` or `SKIPPED`, `PARTIAL_FAILURE` when at least one is `FAILED` alongside a `COMPLETED` one, and `ALL_FAILED` when every variant is `FAILED`.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/core/test_errors.py tests/core/test_results.py tests/cli/test_outcome.py -v`

Expected: FAIL because the new members/types do not exist.

- [ ] **Step 3: Add the dependency and marker**

```toml
[project]
dependencies = [
    # ...existing entries unchanged...
    "pillow-avif-plugin>=1.5,<2",
]

[tool.pytest.ini_options]
markers = ["live_tinify: uses a real Tinify key and consumes quota"]
```

Run: `uv lock`

- [ ] **Step 4: Extend `ErrorCode` and MIME map**

Add `OPTIMIZATION_FAILED = "optimization_failed"` to `ErrorCode`. Add `"image/avif": "avif"` to `MIME_TO_EXTENSION` in `src/pixgen/images/mime.py`.

- [ ] **Step 5: Add the public result contract**

```python
class VariantStatus(StrEnum):
    """Outcome of one planned optimization variant."""

    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class OptimizeVariantResult(BaseModel):
    """Result for a single named optimization variant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="Variant name")
    status: VariantStatus
    artifact_path: Path | None = Field(default=None)
    media_type: str | None = Field(default=None)
    width: int | None = Field(default=None)
    height: int | None = Field(default=None)
    output_bytes: int | None = Field(default=None)
    error: PublicError | None = Field(default=None)


class OptimizeResult(BaseModel):
    """Public result envelope for `pixgen optimize`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    run_id: uuid.UUID
    engine: OptimizeEngine  # imported from pixgen.optimization.models
    source: Path
    source_bytes: int
    total_output_bytes: int = 0
    compression_count_this_month: int | None = None
    variants: tuple[OptimizeVariantResult, ...] = Field(default=())
    error: PublicError | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if bool(self.variants) == (self.error is not None):
            raise ValueError("an optimize result requires variant results or one command error")
        return self
```

`core/results.py` importing `OptimizeEngine` from `pixgen.optimization.models` is the one place this plan lets `core/` depend on a feature package; if that inversion bothers a reviewer, move `OptimizeEngine` itself into `core/models.py` instead — either is acceptable, but pick one and keep it consistent with how `ImageOperation` already lives in `core/models.py`.

- [ ] **Step 6: Extend `CliOutcome`'s union, `exit_status`, and rendering**

In `cli/outcome.py`, add `OptimizeResult` to `type PublicResult = CommandResult | ModelGetResult | ModelListResult | OptimizeResult` and extend `exit_status`:

```python
if isinstance(result, OptimizeResult):
    if result.error is not None:
        return ExitStatus.REJECTED
    completed = sum(v.status is VariantStatus.COMPLETED for v in result.variants)
    failed = sum(v.status is VariantStatus.FAILED for v in result.variants)
    if failed and not completed:
        return ExitStatus.ALL_FAILED
    if failed:
        return ExitStatus.PARTIAL_FAILURE
    return ExitStatus.SUCCESS
```

In `cli/render.py`, add `render_optimize_result(result: OptimizeResult, *, as_json: bool) -> None`, following `render_command_result`'s JSON/interactive/non-interactive split (columns: Variant, Status, Dimensions, Format, Bytes, Path). Wire it into `render_outcome`'s `match` in `cli/outcome.py`.

- [ ] **Step 7: Run the focused tests and quality checks**

Run: `uv run pytest tests/core/test_errors.py tests/core/test_results.py tests/cli/test_outcome.py -v`

Expected: PASS.

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/pixgen/core/errors.py src/pixgen/core/results.py src/pixgen/cli/outcome.py src/pixgen/cli/render.py src/pixgen/images/mime.py tests/core/test_errors.py tests/core/test_results.py tests/cli/test_outcome.py
git commit -m "Extend result, error, and exit contracts for image optimization"
```

### Task 2: Optimization Domain Models and Variant Grammar

**Files:**
- Create: `src/pixgen/optimization/__init__.py`
- Create: `src/pixgen/optimization/models.py`
- Create: `src/pixgen/optimization/planner.py`
- Test: `tests/optimization/test_variant_parser.py`
- Test: `tests/optimization/test_models.py`

**Interfaces:**
- Consumes: `ErrorCode`, `PixgenError` from `pixgen.core.errors`.
- Produces: `OptimizeEngine`, `FormatChoice`, `ImageFormat`, `ResizeMode`, `VariantSpec`, `OptimizeRequest`, `SourceInfo`, `PlannedVariant`, `SkippedVariant`, `OptimizationPlan`, `EngineVariantResult`, `EngineBatchResult`, and `parse_variant(str) -> VariantSpec`.

- [ ] **Step 1: Write failing grammar and model tests**

```python
import pytest

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.optimization.models import ResizeMode
from pixgen.optimization.planner import parse_variant


@pytest.mark.parametrize(
    ("expression", "name", "width", "height", "mode"),
    [
        ("thumbnail=400x400:cover", "thumbnail", 400, 400, ResizeMode.COVER),
        ("content=1280w:scale", "content", 1280, None, ResizeMode.SCALE),
        ("portrait=900h:scale", "portrait", None, 900, ResizeMode.SCALE),
    ],
)
def test_parse_variant_contract(expression, name, width, height, mode) -> None:
    result = parse_variant(expression)
    assert (result.name, result.width, result.height, result.mode) == (
        name,
        width,
        height,
        mode,
    )


@pytest.mark.parametrize(
    "expression",
    [
        "Hero=1200x630:cover",
        "hero_=1200x630:cover",
        "hero=0x630:cover",
        "hero=1200w:cover",
        "hero=1200x630:scale",
        "hero=1200x630:unknown",
    ],
)
def test_invalid_variant_is_stable_invalid_request(expression: str) -> None:
    with pytest.raises(PixgenError) as caught:
        parse_variant(expression)
    assert caught.value.code is ErrorCode.INVALID_REQUEST
```

- [ ] **Step 2: Run the parser tests and verify they fail**

Run: `uv run pytest tests/optimization/test_variant_parser.py tests/optimization/test_models.py -v`

Expected: FAIL because the `optimization` package does not exist.

- [ ] **Step 3: Define the immutable domain models**

Use `ConfigDict(frozen=True, extra="forbid")`, matching the rest of the codebase's Pydantic style. Define:

```python
class OptimizeEngine(StrEnum):
    LOCAL = "local"
    TINIFY = "tinify"


class FormatChoice(StrEnum):
    KEEP = "keep"
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    AVIF = "avif"


class ImageFormat(StrEnum):
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    AVIF = "avif"


class ResizeMode(StrEnum):
    NONE = "none"
    SCALE = "scale"
    FIT = "fit"
    COVER = "cover"
    THUMB = "thumb"


class VariantSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    width: int | None
    height: int | None
    mode: ResizeMode


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: Path
    engine: OptimizeEngine = OptimizeEngine.LOCAL
    variant_expressions: tuple[str, ...] = ()
    web: bool = False
    format: FormatChoice | None = None
    quality: int | None = Field(default=None, ge=1, le=100)
    output: Path | None = None
    output_dir: Path | None = None
    force: bool = False
    create_dirs: bool = False
    dry_run: bool = False


class SourceInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: Path
    format: ImageFormat
    width: int
    height: int
    orientation: int = 1
    byte_length: int
    has_alpha: bool
    has_icc_profile: bool


class PlannedVariant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    index: int
    name: str
    mode: ResizeMode
    requested_width: int | None
    requested_height: int | None
    expected_width: int
    expected_height: int
    output_format: ImageFormat
    destination: Path


class SkippedVariant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    index: int
    name: str
    error: PublicError  # from pixgen.core.results


class OptimizationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: OptimizeRequest
    source: SourceInfo
    quality: int | None
    force: bool
    runnable: tuple[PlannedVariant, ...]
    skipped: tuple[SkippedVariant, ...]
    estimated_compressions_max: int | None = None


class EngineVariantResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    completed: bool
    error: PublicError | None = None


class EngineBatchResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    variants: tuple[EngineVariantResult, ...]
    compression_count_this_month: int | None = None
```

`ResizeMode.NONE` is internal, used for same-dimension optimization, and is rejected by `parse_variant`. `FormatChoice.KEEP` is request-only; `PlannedVariant.output_format` is always a concrete `ImageFormat`. `OptimizationPlan.force` carries the request's `--force` through to the runner so it can pass it to `write_atomic(..., overwrite=plan.force)`.

- [ ] **Step 4: Implement the strict parser**

Compile three anchored regular expressions for `WIDTHxHEIGHT`, `WIDTHw`, and `HEIGHTh`. Accept `scale` only with one dimension and `fit`, `cover`, or `thumb` only with both. Reject names outside `[a-z][a-z0-9-]*` and convert every parse failure to `PixgenError(ErrorCode.INVALID_REQUEST, "Invalid variant definition: {expression!r}")` (the current `PixgenError` takes `code, message` only — there is no `fields=` kwarg like the original draft assumed; put the offending expression in the message text).

- [ ] **Step 5: Run model and parser tests**

Run: `uv run pytest tests/optimization/test_variant_parser.py tests/optimization/test_models.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pixgen/optimization tests/optimization/test_variant_parser.py tests/optimization/test_models.py
git commit -m "Define image optimization domain models"
```

### Task 3: Pure Planning, Source Inspection, and `--web`

**Files:**
- Modify: `src/pixgen/optimization/planner.py`
- Test: `tests/optimization/test_planner.py`
- Test: `tests/optimization/test_source_inspection.py`
- Modify: `tests/factories.py` (or a new `tests/optimization/conftest.py`) for image fixtures

**Interfaces:**
- Consumes: models from Task 2; Pillow `Image` and `ImageOps`.
- Produces: `inspect_source(Path) -> SourceInfo`, `build_plan(OptimizeRequest) -> OptimizationPlan`, constant `WEB_VARIANTS`.

- [ ] **Step 1: Write failing preset, no-upscale, and validation tests**

```python
def test_web_preset_replaces_and_appends_in_stable_order(large_jpeg, tmp_path) -> None:
    request = OptimizeRequest(
        source=large_jpeg,
        web=True,
        variant_expressions=(
            "card=1000x500:cover",
            "portrait=600x900:cover",
        ),
        output_dir=tmp_path,
    )
    plan = build_plan(request)
    assert [item.name for item in plan.runnable] == [
        "thumbnail",
        "card",
        "content",
        "hero",
        "portrait",
    ]
    assert plan.runnable[1].expected_width == 1000
    assert {item.output_format for item in plan.runnable} == {ImageFormat.WEBP}
    assert plan.quality == 82


def test_small_source_skips_cover_but_keeps_valid_scale(small_jpeg, tmp_path) -> None:
    request = OptimizeRequest(
        source=small_jpeg,
        variant_expressions=("card=1200x630:cover", "content=320w:scale"),
        output_dir=tmp_path,
    )
    plan = build_plan(request)
    assert [item.name for item in plan.skipped] == ["card"]
    assert [item.name for item in plan.runnable] == ["content"]


def test_transparent_to_jpeg_fails_before_output_directory_creation(
    transparent_png, tmp_path
) -> None:
    missing = tmp_path / "missing"
    request = OptimizeRequest(
        source=transparent_png,
        format=FormatChoice.JPEG,
        output_dir=missing,
        create_dirs=True,
    )
    with pytest.raises(PixgenError) as caught:
        build_plan(request)
    assert caught.value.code is ErrorCode.INVALID_REQUEST
    assert not missing.exists()
```

- [ ] **Step 2: Add rotated, animated, decoded-format, and collision tests**

Create fixtures for an EXIF-orientation-6 JPEG, a two-frame GIF, an alpha PNG, and a JPEG renamed `.png`. Assert normalized dimensions, `has_alpha`, decoded format, static-image rejection, duplicate explicit-name rejection, local `thumb` rejection, Tinify explicit-quality rejection, `--output` multi-result rejection, output/output-dir mutual exclusion, canonical `.jpg` naming, an all-skipped plan (`plan.runnable == ()`), missing-parent behaviour without `--mkdir`, and no filesystem mutation under `--dry-run`.

Add `large_jpeg`, `small_jpeg`, `transparent_png`, `oriented_jpeg`, and `animated_gif` fixtures near the existing `tests/factories.py` conventions; these are reused by later tasks.

- [ ] **Step 3: Run the planner tests and verify they fail**

Run: `uv run pytest tests/optimization/test_planner.py tests/optimization/test_source_inspection.py -v`

Expected: FAIL because `build_plan` and `inspect_source` do not exist.

- [ ] **Step 4: Implement safe source inspection**

`inspect_source` resolves the path, requires a regular file, opens with Pillow, calls `verify()`, reopens for metadata, rejects `n_frames != 1`, maps the decoded `Image.format` to the four supported formats, reads EXIF orientation tag `274`, computes dimensions after orientation, detects alpha from bands/transparency info, records byte length and ICC presence, and translates Pillow/decompression-bomb failures into `PixgenError(ErrorCode.INVALID_REQUEST, ...)`.

- [ ] **Step 5: Implement deterministic preset merging and dimensions**

Use this exact ordered preset:

```python
WEB_VARIANTS = (
    "thumbnail=400x400:cover",
    "card=1200x630:cover",
    "content=1280w:scale",
    "hero=1920x1080:cover",
)
```

Merge explicit variants by replacing a preset name in place or appending a new name. Reject repeated explicit names. Compute output dimensions with `round()` and a lower bound of one pixel. `scale` skips when its requested axis exceeds the normalized source; `cover` and `thumb` skip when `max(target_width/source_width, target_height/source_height) > 1`; `fit` uses `min(1, width/source_width, height/source_height)` and may therefore produce an unchanged source-sized image.

- [ ] **Step 6: Implement formats, paths, and Tinify cost bounds**

Outside `--web`, default to `keep`; within `--web`, default to WebP and local quality 82. Reject explicit quality for Tinify and for PNG output. Resolve each destination to an absolute path, use `<source-stem>-<variant>.<extension>` with `.jpg`, `.png`, `.webp`, or `.avif`. Default the output directory to `Path.cwd() / "pixgen"` when neither `--output` nor `--output-dir` is given — this matches the fallback `artifacts.plan_output` already uses for `create`/`edit`; do not introduce a separate PlatformDirs-based artifact directory for optimize. Preflight every collision and parent before any credential lookup; with `--mkdir`, validate the nearest existing ancestor without creating anything (directories are created lazily, only for a plan that will actually run). For Tinify, calculate the conservative bound as one upload plus one unit per resize and one unit per conversion among runnable variants; set it to `None` for local plans.

- [ ] **Step 7: Run the planner suite**

Run: `uv run pytest tests/optimization/test_planner.py tests/optimization/test_source_inspection.py -v`

Expected: PASS, including the Review Focus alpha and rotated-dimension cases.

- [ ] **Step 8: Commit**

```bash
git add src/pixgen/optimization/planner.py tests/optimization/test_planner.py tests/optimization/test_source_inspection.py tests/factories.py
git commit -m "Plan website image variants"
```

### Task 4: Batch Protocol and Runner

**Files:**
- Create: `src/pixgen/optimization/base.py`
- Create: `src/pixgen/optimization/runner.py`
- Test: `tests/optimization/test_runner.py`
- Test: `tests/integration/test_atomic_optimization.py`

**Interfaces:**
- Consumes: `OptimizationPlan`, `EngineBatchResult`, `EngineVariantResult` from Task 2; `pixgen.artifacts.write_atomic` for final promotion.
- Produces: private `Optimizer` protocol and `execute_plan(plan: OptimizationPlan, optimizer: Optimizer) -> OptimizeResult` (the caller derives the process exit status from `OptimizeResult` via the `exit_status` extension from Task 1 — the runner itself returns only the result, not an exit code, matching how `CliOutcome.__cyclopts_returncode__` already owns that decision for every other command).

- [ ] **Step 1: Write a fake optimizer and failing ordered-result test**

```python
def create_test_image(path: Path, size: tuple[int, int]) -> None:
    Image.new("RGB", size, "navy").save(path, format="WEBP")


class FakeOptimizer:
    async def optimize(
        self,
        plan: OptimizationPlan,
        staged_paths: Mapping[str, Path],
    ) -> EngineBatchResult:
        results = []
        for variant in reversed(plan.runnable):
            create_test_image(
                staged_paths[variant.name],
                (variant.expected_width, variant.expected_height),
            )
            results.append(EngineVariantResult(name=variant.name, completed=True))
        return EngineBatchResult(variants=tuple(results))


async def test_runner_returns_plan_order(web_plan) -> None:
    result = await execute_plan(web_plan, FakeOptimizer())
    assert [item.name for item in result.variants] == [
        "thumbnail",
        "card",
        "content",
        "hero",
    ]
    assert all(item.status.value == "completed" for item in result.variants)
```

- [ ] **Step 2: Write failing atomicity, metadata, and partial tests**

Cover: a fake engine writes invalid dimensions; a fake engine writes an animated artifact; a fake engine writes EXIF/GPS; the destination already exists and `plan.force` is `False`; one variant reports `optimization_failed`; and one planned variant is a planner-level skip. Assert no invalid artifact is promoted, the old destination's bytes remain unchanged, temporary stage files are removed, successful siblings remain, plan order is stable, and `exit_status(result)` (Task 1) yields `PARTIAL_FAILURE` for a mixed completed/failed batch and `SUCCESS` for a completed/skipped-only batch.

- [ ] **Step 3: Run the runner tests and verify they fail**

Run: `uv run pytest tests/optimization/test_runner.py tests/integration/test_atomic_optimization.py -v`

Expected: FAIL because the protocol and runner do not exist.

- [ ] **Step 4: Define the private protocol**

```python
class Optimizer(Protocol):
    async def optimize(
        self,
        plan: OptimizationPlan,
        staged_paths: Mapping[str, Path],
    ) -> EngineBatchResult: ...
```

`EngineVariantResult` carries only `name`, `completed: bool`, and an optional `PublicError`. `EngineBatchResult` adds optional `compression_count_this_month`; final file locations remain runner-owned.

- [ ] **Step 5: Implement staging and validation**

For each runnable destination, create a unique sibling stage name `.<filename>.pixgen-<uuid>.tmp` in the destination's own parent directory (the parent is created only when `create_dirs` is true, and only for a plan with at least one runnable variant). Reopen every completed stage with Pillow; require one frame, the planned decoded format, exact expected dimensions, empty EXIF, no XMP keys, and no GPS.

- [ ] **Step 6: Promote via `write_atomic`, then clean up and aggregate**

Read each validated stage file's bytes and call `pixgen.artifacts.write_atomic(plan.destination, data, overwrite=plan.force)` — do not reimplement fsync/`os.replace` here; `write_atomic` already owns that guarantee for every other command. Always unlink remaining stage files in `finally`, whether or not promotion succeeded. Merge engine results by variant name into plan order, insert planner skips at their original logical positions, sum only completed output bytes, and build the final `OptimizeResult`. A `write_atomic` failure (e.g. a race on a non-force destination) maps to `PixgenError(ErrorCode.ARTIFACT_FAILURE, ...)` for that one variant, recorded as `VariantStatus.FAILED`, without aborting sibling variants.

- [ ] **Step 7: Run the atomic runner tests**

Run: `uv run pytest tests/optimization/test_runner.py tests/integration/test_atomic_optimization.py -v`

Expected: PASS, including preservation of the pre-existing destination and sibling successes.

- [ ] **Step 8: Commit**

```bash
git add src/pixgen/optimization/base.py src/pixgen/optimization/runner.py tests/optimization/test_runner.py tests/integration/test_atomic_optimization.py
git commit -m "Add atomic optimization runner"
```

### Task 5: Local Pillow Optimizer

**Files:**
- Create: `src/pixgen/optimization/local.py`
- Test: `tests/optimization/test_local.py`
- Test: `tests/integration/test_local_optimization.py`

**Interfaces:**
- Consumes: private `Optimizer`, `OptimizationPlan`, runner-owned staged paths, `pillow_avif` plugin registration.
- Produces: `LocalOptimizer.optimize(...) -> EngineBatchResult`.

- [ ] **Step 1: Register the AVIF plugin and write failing resize/one-decode tests**

At module import time in `local.py`:

```python
import pillow_avif  # noqa: F401  # registers AVIF with Pillow's plugin registry
```

```python
from pixgen.optimization import local as local_module


async def test_local_web_batch_decodes_once(web_plan, monkeypatch) -> None:
    opens = 0
    original = local_module._load_source

    def counted_load(*args, **kwargs):
        nonlocal opens
        opens += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(local_module, "_load_source", counted_load)
    result = await execute_plan(web_plan, LocalOptimizer())
    assert opens == 1
    assert [(item.width, item.height) for item in result.variants] == [
        (400, 400),
        (1200, 630),
        (1280, 853),
        (1920, 1080),
    ]
```

Use a fixture whose proportions make the expected `round()` result unambiguous. Add tests for proportional width/height scale, contain-style `fit`, centered exact `cover`, same-dimension output, and one AVIF round-trip (encode then decode with `pillow_avif` registered).

- [ ] **Step 2: Write failing metadata and format tests**

For JPEG, PNG, WebP, and AVIF fixtures, assert output decodability and decoded format. Use an orientation-6 JPEG with EXIF/GPS/XMP and an ICC profile; assert pixels are upright, EXIF/GPS/XMP are absent, and the ICC profile survives where Pillow's encoder supports it. Assert `--web` uses quality 82 by spying on save keyword arguments, and that an explicit `--quality` replaces it.

- [ ] **Step 3: Run the local tests and verify they fail**

Run: `uv run pytest tests/optimization/test_local.py tests/integration/test_local_optimization.py -v`

Expected: FAIL because `LocalOptimizer` does not exist.

- [ ] **Step 4: Implement one-decode transformations**

Implement private `_load_source(path: Path) -> Image.Image`; it opens once, calls `load()`, applies `ImageOps.exif_transpose()`, copies the normalized image, closes the file handle, and returns the in-memory copy with source ICC bytes retained. Process variants sequentially. Use `Image.Resampling.LANCZOS`; use `resize()` for scale, `ImageOps.contain()` for fit, `ImageOps.fit(..., centering=(0.5, 0.5))` for cover, and `copy()` for internal `NONE`.

> **Coordination note:** `_load_source` and the encode step below (`_encode_variant`, added in Step 5) do exactly what `docs/superpowers/plans/2026-09-27-media-commands.md`'s Task 3 (`media/transform.py`, `sanitize_image`) also needs — decode once, apply EXIF orientation, strip metadata, re-encode. If that plan lands after this one, its author should import these two functions from `pixgen.optimization.local` instead of duplicating them; if it lands first, this task should import its equivalents instead. Whoever implements second should flag the duplication in that PR rather than silently keeping two copies.

- [ ] **Step 5: Implement metadata-safe encoding**

Construct save keyword arguments from scratch so EXIF and XMP are never copied. Pass `icc_profile` only when present and supported. Convert non-alpha JPEG output to `RGB`; use `quality=plan.quality` and `optimize=True` for JPEG/WebP/AVIF when quality is set, and `optimize=True` for PNG. Catch each variant's decode/resize/encode exception, delete its stage file, and return `EngineVariantResult(name=..., completed=False, error=PublicError(code=ErrorCode.OPTIMIZATION_FAILED, message=...))` for that variant while continuing the batch.

- [ ] **Step 6: Run the local engine and runner suites**

Run: `uv run pytest tests/optimization/test_local.py tests/integration/test_local_optimization.py tests/optimization/test_runner.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pixgen/optimization/local.py tests/optimization/test_local.py tests/integration/test_local_optimization.py
git commit -m "Optimize image variants locally"
```

### Task 6: Tinify Configuration and Single-Output HTTP Contract

**Files:**
- Modify: `src/pixgen/config/models.py`
- Create: `src/pixgen/optimization/tinify.py`
- Test: `tests/config/test_models.py`
- Test: `tests/providers/test_tinify.py`

**Interfaces:**
- Consumes: `Settings.tinify_api_key`, HTTPX2 `AsyncClient`, `MockTransport`, Pydantic `SecretStr`.
- Produces: `TinifyOptimizer`, `_validate_output_url(str) -> httpx2.URL`.

- [ ] **Step 1: Write failing settings tests**

```python
def test_tinify_key_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TINIFY_API_KEY", "environment-secret")
    settings = Settings()
    assert settings.tinify_api_key is not None
    assert settings.tinify_api_key.get_secret_value() == "environment-secret"


def test_tinify_key_defaults_to_none(monkeypatch) -> None:
    monkeypatch.delenv("TINIFY_API_KEY", raising=False)
    monkeypatch.delenv("PIXGEN_TINIFY_API_KEY", raising=False)
    assert Settings().tinify_api_key is None
```

Also assert `PixgenError(ErrorCode.CREDENTIAL_UNAVAILABLE, ...)` is what `TinifyOptimizer`'s construction path raises when `settings.tinify_api_key` is `None`, and that the secret never appears in that exception's string form.

- [ ] **Step 2: Write failing HTTP upload, URL, and auth tests**

```python
async def test_same_size_tinify_uploads_once_and_downloads_once(tinify_plan, tmp_path) -> None:
    requests: list[httpx2.Request] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path == "/shrink":
            return httpx2.Response(
                201,
                headers={
                    "Location": "https://api.tinify.com/output/abc123",
                    "Compression-Count": "17",
                },
                json={"input": {"size": 100, "type": "image/jpeg"}},
            )
        return image_response(TEST_JPEG_BYTES, count=17)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    optimizer = TinifyOptimizer(client, SecretStr("secret-canary"))
    output = await optimizer.optimize(tinify_plan, {"optimized": tmp_path / "x.tmp"})
    assert [request.method for request in requests] == ["POST", "GET"]
    assert output.compression_count_this_month == 17
```

Define `image_response(data: bytes, *, count: int) -> httpx2.Response` and deterministic `TEST_JPEG_BYTES` at the top of `tests/providers/test_tinify.py`; the bytes must decode to the dimensions expected by `tinify_plan`. Parameterize malicious `Location` values for HTTP scheme, another host, user info, non-default port, query, fragment, `/other/token`, and encoded traversal. Assert only the upload request occurs. Add 401, 429, 5xx, timeout, and transport-failure mapping tests with secret-canary assertions.

- [ ] **Step 3: Run settings and Tinify tests and verify they fail**

Run: `uv run pytest tests/config/test_models.py tests/providers/test_tinify.py -v`

Expected: FAIL because `Settings.tinify_api_key` and `TinifyOptimizer` do not exist.

- [ ] **Step 4: Add the settings field**

```python
tinify_api_key: SecretStr | None = Field(
    default=None,
    validation_alias=AliasChoices("PIXGEN_TINIFY_API_KEY", "TINIFY_API_KEY"),
    description="Tinify API key",
)
```

Place it next to `openai_api_key`/`gemini_api_key` in `Settings`. No new module, no backend abstraction — this is the entire credential story.

- [ ] **Step 5: Implement upload and strict output URL validation**

Create an HTTPX2 `BasicAuth("api", secret)` and explicit `Timeout(connect=10, read=60, write=60, pool=10)`. `POST https://api.tinify.com/shrink` once with binary content. Accept only a `201` upload response. Validate the returned URL by parsed components: scheme `https`, host exactly `api.tinify.com`, port absent or 443, no username/password/query/fragment, and path matching `^/output/[A-Za-z0-9]+$` after rejecting encoded separators or dot segments.

- [ ] **Step 6: Implement same-size safe download and error translation**

For `ResizeMode.NONE` with unchanged format, stream one authenticated GET into the runner stage. Translate 401/403 to `ErrorCode.AUTHENTICATION_FAILED`, 429 to `ErrorCode.RATE_LIMITED`, 5xx/transport errors to `ErrorCode.PROVIDER_UNAVAILABLE`, and HTTPX2 timeouts to `ErrorCode.TIMEOUT`. Use fixed safe messages; discard response bodies and URLs. Do not retry any request in this task.

- [ ] **Step 7: Run the contract tests**

Run: `uv run pytest tests/config/test_models.py tests/providers/test_tinify.py -v`

Expected: PASS, including the SSRF and secret-canary cases.

- [ ] **Step 8: Commit**

```bash
git add src/pixgen/config/models.py src/pixgen/optimization/tinify.py tests/config/test_models.py tests/providers/test_tinify.py
git commit -m "Integrate Tinify upload contract"
```

### Task 7: Tinify Variants, Orientation, Concurrency, and Safe Retry

**Files:**
- Modify: `src/pixgen/optimization/tinify.py`
- Modify: `tests/providers/test_tinify.py`
- Create: `tests/integration/test_tinify_batch.py`
- Create: `tests/live/test_tinify_live.py`

**Interfaces:**
- Consumes: `TinifyOptimizer` from Task 6 and all planned resize modes.
- Produces: complete batch behaviour with maximum concurrency four, ordered engine results, safe-GET retry, normalized oriented uploads, and conservative count capture.

- [ ] **Step 1: Write failing derivative payload and ordering tests**

Use `MockTransport` to delay responses so completion order is hero, thumbnail, content, card. Assert exactly one `/shrink` upload, at most four active derivative requests, result order equal to plan order, and these bodies:

```json
{"resize":{"method":"cover","width":400,"height":400},"convert":{"type":"image/webp"}}
```

```json
{"resize":{"method":"scale","width":1280},"convert":{"type":"image/webp"}}
```

Assert `thumb` maps directly to Tinify `thumb`, `fit` includes both bounds, and no `convert` object is sent when the source and destination formats match.

- [ ] **Step 2: Write failing retry and partial-failure tests**

Assert upload and derivative POST connection failures produce one attempt only. For the same-size GET, return 503 with `Retry-After: 1`, then a transport error, then success; inject a fake sleeper and zero jitter and assert three attempts and recorded delays. Make one derivative return 500 containing `secret-canary`; assert other files complete, the failed result is sanitized, plan order is retained, and `exit_status(result)` (Task 1) is `PARTIAL_FAILURE`.

- [ ] **Step 3: Write the rotated-upload test**

Build an orientation-6 JPEG containing EXIF/GPS/XMP. Capture the `/shrink` body, reopen it with Pillow, and assert normalized dimensions, no EXIF/GPS/XMP, preserved ICC when supported, and one upload. Assert the temporary normalized source is removed after both success and upload failure. For orientation 1, assert upload bytes exactly equal original bytes.

- [ ] **Step 4: Run the expanded Tinify suite and verify failures**

Run: `uv run pytest tests/providers/test_tinify.py tests/integration/test_tinify_batch.py -v`

Expected: FAIL because derivative batching, normalization, and retry are absent.

- [ ] **Step 5: Implement the one-time normalized upload source**

When `plan.source.orientation != 1`, use Pillow to load and `ImageOps.exif_transpose` once, save a private temporary file in the system temp directory in the source format with EXIF/XMP omitted and ICC retained, upload its bytes, and unlink it in `finally`. Use JPEG quality 95 with optimization for the exceptional orientation rewrite. Upload original bytes unchanged for orientation 1.

- [ ] **Step 6: Implement derivative requests and bounded concurrency**

Build one JSON object per runnable variant, combining `resize` and `convert` when both apply. Use `asyncio.Semaphore(4)` and create tasks in plan order; store each task's result by original index. Stream derivative POST bodies directly to the assigned stage, never follow redirects, never retry, and continue other derivatives after an individual failure. Track the maximum valid `Compression-Count` header seen because concurrent responses can arrive out of order.

- [ ] **Step 7: Implement bounded safe-GET retry**

Allow three total attempts only for GET. Delay by a valid nonnegative numeric `Retry-After` capped at 30 seconds, otherwise exponential delays `0.25`, `0.5` plus injected jitter in `[0, 0.25]`. Retry transport failures, timeouts, 429, and 5xx; do not retry authentication or other 4xx responses. Inject `sleep` and `jitter` callables so tests do not wait.

- [ ] **Step 8: Add the opt-in live smoke test**

Mark with `@pytest.mark.live_tinify`, require both `PIXGEN_RUN_LIVE_TINIFY=1` and `TINIFY_API_KEY`, create one tiny PNG, run same-dimension Tinify optimization, and assert a decodable output plus returned compression count. The extra opt-in variable keeps ordinary pytest and CI non-billable even on a machine that happens to have a Tinify key; the test name and docstring must state that it consumes quota.

- [ ] **Step 9: Run mock tests, leaving live tests unselected**

Run: `uv run pytest tests/providers/test_tinify.py tests/integration/test_tinify_batch.py -v`

Expected: PASS with no external network access.

- [ ] **Step 10: Commit**

```bash
git add src/pixgen/optimization/tinify.py tests/providers/test_tinify.py tests/integration/test_tinify_batch.py tests/live/test_tinify_live.py
git commit -m "Add Tinify image variants"
```

### Task 8: `pixgen optimize` CLI and Machine Contract

**Files:**
- Create: `src/pixgen/cli/optimize.py`
- Modify: `src/pixgen/cli/app.py`
- Test: `tests/cli/test_optimize.py`
- Test: `tests/integration/test_optimize_subprocess.py`

**Interfaces:**
- Consumes: `build_plan`, `LocalOptimizer`, `TinifyOptimizer`, `execute_plan`, `render_optimize_result` (Task 1), `CliOutcome`/`cli_command` (existing `cli/outcome.py`).
- Produces: root-level `pixgen optimize SOURCE` with the complete approved option contract, following the same registration shape as `create`/`edit` in `cli/image.py`.

- [ ] **Step 1: Write failing help and local subprocess tests**

Follow the existing subprocess-invocation pattern already used for `create`/`edit` CLI tests (check `tests/cli/` for the current fixture name and helper rather than assuming `run_pixgen` exists — add it only if no equivalent helper is already there).

```python
def test_optimize_help_exposes_approved_options(run_pixgen) -> None:
    completed = run_pixgen("optimize", "--help")
    assert completed.returncode == 0
    for option in (
        "--engine",
        "--variant",
        "--web",
        "--format",
        "--quality",
        "--output",
        "--output-dir",
        "--dry-run",
        "--force",
        "--mkdir",
        "--json",
    ):
        assert option in completed.stdout


def test_web_local_subprocess_writes_four_variants(run_pixgen, large_jpeg, tmp_path):
    completed = run_pixgen(
        "optimize",
        str(large_jpeg),
        "--web",
        "--output-dir",
        str(tmp_path),
        "--json",
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert [item["name"] for item in payload["variants"]] == [
        "thumbnail",
        "card",
        "content",
        "hero",
    ]
    assert completed.stderr == ""
```

- [ ] **Step 2: Write failing dry-run and partial tests**

Inject a client factory that fails if touched; run `--engine tinify --web --dry-run --mkdir` with `TINIFY_API_KEY` unset and assert one JSON plan-preview payload, no HTTP call, and no directory created. Assert a batch with one engine failure returns `ExitStatus.PARTIAL_FAILURE` (4) with completed files preserved, and a fatal validation error (e.g. malformed `--variant`) emits one `OptimizeResult`-shaped error envelope with nothing partial written.

- [ ] **Step 3: Run CLI tests and verify failures**

Run: `uv run pytest tests/cli/test_optimize.py tests/integration/test_optimize_subprocess.py -v`

Expected: FAIL because the command is not registered.

- [ ] **Step 4: Declare the Cyclopts command**

In `src/pixgen/cli/optimize.py`, mirror `build_operation_app` from `cli/image.py`: an `App(name="optimize", group="Operations")` with `@app.default @cli_command() async def optimize(source: Path, *, engine: OptimizeEngine = OptimizeEngine.LOCAL, variant: list[str] | None = None, web: bool = False, format: FormatChoice | None = None, quality: int | None = None, output: Path | None = None, output_dir: Path | None = None, dry_run: bool = False, force: bool = False, mkdir: bool = False, json: bool = False) -> CliOutcome`. Preserve `None` for omitted `format`/`quality` so the planner can distinguish explicit values from preset defaults. `cli_command()` already turns `PixgenError`/`ValidationError` into a rejected `CliOutcome` — reuse it exactly as `create`/`edit` do rather than adding a second error-catching layer.

- [ ] **Step 5: Compose only the selected engine after planning**

Call `build_plan` first. For `--dry-run`, render the plan (as a preview, not an `OptimizeResult`) and return without constructing an optimizer or client. For `local`, construct only `LocalOptimizer` (with `pillow_avif` already registered by `optimization/local.py`'s import). For `tinify`, read `settings.tinify_api_key` only after planning succeeds, raise `PixgenError(ErrorCode.CREDENTIAL_UNAVAILABLE, ...)` if it is `None`, then build an HTTPX2 client with redirects disabled, pass it to `TinifyOptimizer`, and close it after `execute_plan`.

- [ ] **Step 6: Return the outcome**

Wrap the `OptimizeResult` from `execute_plan` in `CliOutcome(result, as_json=json)`, matching `create`/`edit`. `render_outcome`/`exit_status` (Task 1) already own JSON vs. human rendering and the process exit code — the command function does not compute either itself.

- [ ] **Step 7: Register the command**

In `cli/app.py`'s `build_app`, add `app.command(build_optimize_app(runtime_dependency))` alongside the existing `app.command(...)` calls for `create`/`edit`/`model`.

- [ ] **Step 8: Run CLI and subprocess tests**

Run: `uv run pytest tests/cli/test_optimize.py tests/integration/test_optimize_subprocess.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/pixgen/cli/optimize.py src/pixgen/cli/app.py tests/cli/test_optimize.py tests/integration/test_optimize_subprocess.py
git commit -m "Add pixgen optimize command"
```

### Task 9: Passive Info and Optional Tinify Doctor Check

**Files:**
- Create: `src/pixgen/cli/system.py`
- Modify: `src/pixgen/cli/app.py`
- Modify: `src/pixgen/optimization/tinify.py`
- Test: `tests/cli/test_info.py`
- Test: `tests/cli/test_doctor.py`

**Interfaces:**
- Consumes: Pillow's feature registry (with `pillow_avif` registered), `Settings.tinify_api_key`, injected HTTPX2 client.
- Produces: `collect_info(...) -> InfoResult`, `check_tinify_auth(...) -> DiagnosticCheck`, `pixgen info`, `pixgen doctor [--tinify]`.

- [ ] **Step 1: Write failing passive-info tests**

Assert `info --json` reports Pixgen/Python/Pillow versions, actual local read/write capability for PNG/JPEG/WebP/AVIF (post `pillow_avif` registration), and whether `Settings.tinify_api_key` is configured (a bare boolean — there is only one credential source now, so no `CredentialSource` enum is needed). Inject a network client that raises if called and assert no request or filesystem write occurs.

- [ ] **Step 2: Write failing doctor tests**

Cover: no key and no `--tinify` yields a stable skipped check with no network; explicit `--tinify` with no key yields a failed check with `ErrorCode.CREDENTIAL_UNAVAILABLE`; a configured key sends one empty `POST /shrink`; an expected 400 client-data response is `ok`; 429 proves authentication but returns `warning`; 401/403 is a failed authentication check; transport and timeout failures use safe failed checks. Assert the secret and response body never appear.

- [ ] **Step 3: Run diagnostics tests and verify failures**

Run: `uv run pytest tests/cli/test_info.py tests/cli/test_doctor.py -v`

Expected: FAIL because diagnostics are not registered.

- [ ] **Step 4: Implement passive capability reporting**

Initialize Pillow's plugin registry (importing `pixgen.optimization.local` is enough to register AVIF), derive supported read/write formats from Pillow rather than hard-coding availability, and expose only a boolean for Tinify credential presence. Do not resolve or expose the secret value.

- [ ] **Step 5: Implement the explicit Tinify auth probe**

Send exactly one authenticated empty-body `POST https://api.tinify.com/shrink`. Treat 400-class client-data errors other than 401/403 as proof the credential was accepted; make 429 a warning because it proves auth while reporting an account/rate condition. Never retry and never upload image bytes.

- [ ] **Step 6: Register and render diagnostics**

Support human and `schema_version: Literal["1"]` JSON for both commands, following the same `render_*` split as Task 1's `render_optimize_result`. `doctor` runs the Tinify check only when a credential is configured or `--tinify` is explicit. Map to `ExitStatus`: `SUCCESS` when checks are only ok/warning/skipped, `REJECTED` for missing/invalid credentials or provider/network/timeout failures (these are command-level diagnostic failures, not partial batches — there is nothing to partially complete).

- [ ] **Step 7: Run diagnostics tests**

Run: `uv run pytest tests/cli/test_info.py tests/cli/test_doctor.py -v`

Expected: PASS with all network behaviour supplied by `MockTransport`.

- [ ] **Step 8: Commit**

```bash
git add src/pixgen/cli/system.py src/pixgen/cli/app.py src/pixgen/optimization/tinify.py tests/cli/test_info.py tests/cli/test_doctor.py
git commit -m "Diagnose image optimization engines"
```

### Task 10: Documentation, Agent Skill, and Release Verification

**Files:**
- Modify: `README.md`
- Create: `docs/image-optimization.md`
- Create or modify: `skills/pixgen/SKILL.md` and `skills/pixgen/references/image-optimization.md`
- Test: `tests/test_documented_commands.py`

**Interfaces:**
- Consumes: the final CLI and schema contracts.
- Produces: user documentation, provider-neutral agent instructions, command-smoke coverage.

- [ ] **Step 1: Write failing documentation tests**

```python
def test_documented_web_command_runs(run_pixgen, large_jpeg, tmp_path) -> None:
    completed = run_pixgen(
        "optimize",
        str(large_jpeg),
        "--web",
        "--output-dir",
        str(tmp_path),
        "--json",
    )
    assert completed.returncode == 0


def test_agent_skill_references_stable_json_contract() -> None:
    skill = Path("skills/pixgen/SKILL.md").read_text()
    reference = Path("skills/pixgen/references/image-optimization.md").read_text()
    assert "pixgen optimize" in skill
    assert "optimization_failed" in reference
    assert "TINIFY_API_KEY" in reference
```

- [ ] **Step 2: Run the documentation tests and verify failures**

Run: `uv run pytest tests/test_documented_commands.py -v`

Expected: FAIL because the docs and skill content do not exist yet.

- [ ] **Step 3: Write user documentation**

Document local same-size optimization, custom scale/fit/cover variants, the four exact `--web` outputs, explicit Tinify `thumb`, format/quality rules, no-upscale skips, the `ExitStatus.PARTIAL_FAILURE` case, force/create-dir behaviour, dry-run cost bounds, `TINIFY_API_KEY`, metadata removal, Tinify upload privacy, and current billing links. State that prices can change and the returned compression count is authoritative. Note that `--web` output defaults to WebP and needs no AVIF plugin, but AVIF *input* or `--format avif` does.

- [ ] **Step 4: Write or extend the provider-neutral Agent Skill**

Teach agents to prefer local mode, use `--json`, inspect dry-run output, select Tinify only when remote upload and billing are acceptable, retain successful paths on a partial-failure exit, branch on stable `ErrorCode` values, and run `pixgen doctor --tinify --json` for Tinify setup failures. Keep raw HTTP payloads, provider URLs, and direct SDK instructions out of the skill.

- [ ] **Step 5: Run the complete non-live test suite**

Run: `uv run pytest -m "not live_tinify" -v`

Expected: PASS; no external Tinify request occurs.

- [ ] **Step 6: Run all static and repository checks**

Run: `just lint`

Expected: PASS with no remaining formatter changes.

Run: `just type-check`

Expected: PASS.

Run: `just test`

Expected: PASS with live Tinify skipped.

Run: `just check`

Expected: PASS.

- [ ] **Step 7: Optionally run the billable live smoke test only with explicit approval**

Run: `PIXGEN_RUN_LIVE_TINIFY=1 uv run pytest -m live_tinify tests/live/test_tinify_live.py -v`

Expected: PASS and consume Tinify quota. Do not run this step without a configured test key and explicit confirmation for that billable request.

- [ ] **Step 8: Commit**

```bash
git add README.md docs/image-optimization.md skills/pixgen tests/test_documented_commands.py
git commit -m "Document image optimization workflows"
```

- [ ] **Step 9: Request final code review**

Use `superpowers:requesting-code-review` to review the complete branch against `docs/superpowers/specs/2026-09-19-image-optimization-design.md`, this implementation plan, the stable machine schema, paid-request retry policy, secret handling, and atomic artifact guarantees. Resolve findings, rerun Steps 5-6, and then use `superpowers:finishing-a-development-branch` for the integration decision.
