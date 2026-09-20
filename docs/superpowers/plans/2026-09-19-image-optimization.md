# Website Image Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `pixgen image optimize` command that creates website-ready image variants locally with Pillow or explicitly through Tinify using HTTPX2.

**Architecture:** A pure planner inspects and validates the source, expands presets, applies no-upscale rules, and resolves destinations before credentials or network access. A private batch `Optimizer` boundary supports a sequential Pillow implementation and a bounded-concurrency Tinify implementation; a runner owns staged files, artifact validation, atomic promotion, ordered partial results, and exit classification. The feature introduces only the CLI, error, credential, output, and path foundations needed by optimization and does not implement generation or SQLite persistence.

**Tech Stack:** Python 3.14, Cyclopts 4, Pydantic 2, Pillow 12.3, HTTPX2 2.12, keyring, Rich, pytest, Ruff, Pyrefly, prek.

**Spec:** `docs/superpowers/specs/2026-09-19-image-optimization-design.md`

## Global Constraints

- Python remains `>=3.14`; add `pillow>=12.3,<13` and do not add the Tinify Python SDK or `requests`.
- The only entry point is the standalone `pixgen image optimize` command; generated images are never optimized implicitly.
- `local` is the default, offline engine. `tinify` is selected explicitly and is the only action that authorizes source upload and possible API charges.
- Support only static PNG, JPEG, WebP, and AVIF; reject animated images, SVG, video, and transparent-to-JPEG conversion.
- Never upscale. Keep valid completed variants when another variant is skipped or fails.
- Normalize EXIF orientation, strip EXIF/XMP/GPS, and retain ICC locally where the encoder supports it; Tinify output does not promise ICC retention.
- Never overwrite without `--force`, never create missing parents without `--mkdir`, and promote only validated, fsynced sibling temporary files with `os.replace`.
- `--dry-run` performs no credential lookup, network request, file write, or directory creation.
- Do not persist optimization runs in SQLite and do not add a public optimizer plugin API.
- Never retry `POST /shrink` or Tinify derivative `POST` requests. Retry only safe `GET` downloads, with a bound, jitter, and `Retry-After` support.
- Validate Tinify output URLs as exact HTTPS `api.tinify.com/output/<token>` URLs before following them; never expose credentials, authorization headers, provider bodies, or output URLs.
- JSON is schema version 1, variant order is plan order, and exit codes remain 0 success, 1 internal, 2 usage/validation/configuration, 3 credentials/authentication, 4 provider/network/rate limit, 5 timeout, 6 optimization failure or partial result, and 7 artifact/storage failure.

## Review Focus

- A JPEG whose EXIF orientation swaps width and height must be planned against normalized dimensions; Tinify must upload one normalized, metadata-free intermediate and clean it up.
- A transparent source requested as JPEG must fail before credential lookup, directory creation, or network access.
- A malicious Tinify `Location` such as another host, user-info URL, query-bearing URL, or deceptive `/output/../` path must be rejected without a follow-up request.
- A failed replacement must leave the old destination byte-for-byte intact, remove temporary files, and preserve already promoted sibling variants.
- Concurrent Tinify responses that complete out of order, including one derivative failure, must still return planned order, retain successes, sanitize the failure, and exit with the correct category precedence.

---

## File Map

### Project and shared foundations

- Modify `pyproject.toml` for Pillow, pytest markers, and the real console entry point.
- Modify `uv.lock` through `uv lock` after dependency changes.
- Modify `justfile` to run `pixgen`, Pyrefly, and the existing quality suite correctly.
- Modify `.gitignore` to ignore `.superpowers/` visual-companion state.
- Modify `src/pixgen/__init__.py` to expose only `__version__`.
- Create `src/pixgen/__main__.py` as the module-entry delegate.
- Create `src/pixgen/core/__init__.py` and `src/pixgen/core/errors.py` for stable safe errors and exit mapping.
- Create `src/pixgen/output.py` for JSON/human stream policy.
- Create `src/pixgen/cli/__init__.py`, `src/pixgen/cli/app.py`, `src/pixgen/cli/image.py`, and `src/pixgen/cli/system.py` for the real Cyclopts command tree.
- Create `src/pixgen/config/paths.py` for the standard artifact directory.
- Fix `src/pixgen/config/models.py` so Pydantic Settings imports and defaults are valid on Pydantic 2.
- Create `src/pixgen/credentials.py` for keyring-first Tinify secret resolution.

### Optimization subsystem

- Create `src/pixgen/optimization/__init__.py` for the private package surface.
- Create `src/pixgen/optimization/models.py` for requests, source facts, plans, engine outputs, and versioned results.
- Create `src/pixgen/optimization/planner.py` for variant parsing, `--web` merging, source inspection, capability checks, cost bounds, and destinations.
- Create `src/pixgen/optimization/base.py` for the private batch protocol.
- Create `src/pixgen/optimization/local.py` for one-decode Pillow transformations.
- Create `src/pixgen/optimization/tinify.py` for direct HTTPX2 upload, transformations, safe reads, and error translation.
- Create `src/pixgen/optimization/runner.py` for staging, validation, promotion, cleanup, partial aggregation, and exit precedence.

### Tests, docs, and agent guidance

- Create focused tests under `tests/unit/{core,credentials,optimization,output}/`, `tests/providers/`, `tests/cli/`, `tests/integration/`, and `tests/live/`.
- Create `tests/conftest.py` for deterministic static, animated, transparent, and oriented image fixtures plus subprocess CLI invocation.
- Create `docs/image-optimization.md` and update `README.md`.
- Create `skills/pixgen/SKILL.md` and `skills/pixgen/references/image-optimization.md`.

---

### Task 1: Runnable CLI and Stable Error Foundation

**Files:**
- Modify: `pyproject.toml:1-36`
- Modify: `uv.lock`
- Modify: `justfile:1-51`
- Modify: `.gitignore`
- Modify: `src/pixgen/__init__.py:1-2`
- Modify: `src/pixgen/config/models.py:1-25`
- Create: `src/pixgen/__main__.py`
- Create: `src/pixgen/cli/__init__.py`
- Create: `src/pixgen/cli/app.py`
- Create: `src/pixgen/core/__init__.py`
- Create: `src/pixgen/core/errors.py`
- Create: `src/pixgen/output.py`
- Test: `tests/unit/core/test_errors.py`
- Test: `tests/unit/output/test_output.py`
- Test: `tests/cli/test_entrypoint.py`

**Interfaces:**
- Consumes: Cyclopts `App`; Pydantic `BaseModel`; Rich `Console`.
- Produces: `ErrorCode`, `ErrorDetail`, `ErrorEnvelope`, `PixgenError`, `exit_code_for_error(ErrorCode) -> int`, `write_json(BaseModel, TextIO) -> None`, `write_error(PixgenError, TextIO) -> int`, root `app`, and `main() -> None`.

- [ ] **Step 1: Write failing stable-error tests**

```python
from pixgen.core.errors import ErrorCode, PixgenError, exit_code_for_error


def test_optimization_failure_has_stable_exit_six() -> None:
    error = PixgenError(ErrorCode.OPTIMIZATION_FAILED, "Could not encode card.")
    assert error.detail.model_dump(mode="json") == {
        "code": "optimization_failed",
        "message": "Could not encode card.",
        "retryable": False,
        "provider": None,
        "fields": {},
    }
    assert exit_code_for_error(error.detail.code) == 6


def test_error_text_never_includes_cause_repr() -> None:
    error = PixgenError(
        ErrorCode.PROVIDER_UNAVAILABLE,
        "Tinify is unavailable.",
        retryable=True,
    )
    assert "secret-canary" not in str(error)
```

- [ ] **Step 2: Write failing output and entry-point tests**

```python
import json
import subprocess
import sys
from io import StringIO

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.output import write_error


def test_json_error_is_one_document_on_stderr() -> None:
    stream = StringIO()
    exit_code = write_error(
        PixgenError(ErrorCode.INVALID_REQUEST, "Bad variant."), stream
    )
    assert exit_code == 2
    assert json.loads(stream.getvalue())["error"]["code"] == "invalid_request"
    assert stream.getvalue().count("\n") == 1


def test_module_entrypoint_exposes_image_namespace() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pixgen", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "image" in completed.stdout
```

- [ ] **Step 3: Run the focused tests and verify the missing-module failures**

Run: `uv run pytest tests/unit/core/test_errors.py tests/unit/output/test_output.py tests/cli/test_entrypoint.py -v`

Expected: FAIL because `pixgen.core.errors`, `pixgen.output`, and the CLI package do not exist.

- [ ] **Step 4: Add dependencies, entry points, and development commands**

Set these exact project values and regenerate the lock:

```toml
[project]
requires-python = ">=3.14"
dependencies = [
    "cyclopts>=4.25.2,<5",
    "httpx2>=2.12.0,<3",
    "keyring>=25.7.0",
    "pillow>=12.3,<13",
    "platformdirs>=4.0",
    "pydantic>=2.13.5",
    "pydantic-settings>=2.15.0",
    "rich>=15.0.0",
    "sqlmodel>=0.0.42",
    "stamina>=26.1.0",
]

[project.scripts]
pixgen = "pixgen.cli.app:main"

[tool.pytest.ini_options]
markers = ["live_tinify: uses a real Tinify key and consumes quota"]
```

Run: `uv lock`

Change `just run` to `uv run pixgen`, replace the stale `type-check-ty` recipe with `type-check: uv run pyrefly check`, and add `.superpowers/` to `.gitignore`.

- [ ] **Step 5: Implement the safe error contract**

```python
class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_CONFIGURATION = "invalid_configuration"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    MODEL_NOT_FOUND = "model_not_found"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    GENERATION_FAILED = "generation_failed"
    GENERATION_CANCELLED = "generation_cancelled"
    OPTIMIZATION_FAILED = "optimization_failed"
    TIMEOUT = "timeout"
    ARTIFACT_ERROR = "artifact_error"
    STORAGE_ERROR = "storage_error"
    INTERNAL_ERROR = "internal_error"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: ErrorCode
    message: str
    retryable: bool = False
    provider: str | None = None
    fields: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    schema_version: Literal[1] = 1
    error: ErrorDetail
```

`PixgenError` accepts only the safe fields above; store an exception cause with `raise ... from cause`, never in `message` or `fields`. Map codes to the exact global exit table and default unknown failures to exit 1.

- [ ] **Step 6: Implement JSON output and the CLI shell**

```python
def write_json(model: BaseModel, stream: TextIO) -> None:
    stream.write(model.model_dump_json(exclude_none=False) + "\n")


def write_error(error: PixgenError, stream: TextIO = sys.stderr) -> int:
    write_json(ErrorEnvelope(error=error.detail), stream)
    return exit_code_for_error(error.detail.code)
```

Create a root Cyclopts `App(name="pixgen", version=__version__)`, attach an empty `image_app = App(name="image")`, and make both `pixgen` and `python -m pixgen` call the same `main()`. Correct `config/models.py` to import `BaseSettings` and `SettingsConfigDict` from `pydantic_settings`, use `Field(default_factory=...)`, and avoid `Path.cwd()` as a class-level default.

- [ ] **Step 7: Run the focused tests and quality checks**

Run: `uv run pytest tests/unit/core/test_errors.py tests/unit/output/test_output.py tests/cli/test_entrypoint.py -v`

Expected: PASS.

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check`

Expected: PASS.

- [ ] **Step 8: Commit the foundation**

```bash
git add .gitignore pyproject.toml uv.lock justfile src/pixgen tests/unit/core tests/unit/output tests/cli/test_entrypoint.py
git commit -m "Build image optimization CLI foundation"
```

### Task 2: Optimization Domain Models and Variant Grammar

**Files:**
- Create: `src/pixgen/optimization/__init__.py`
- Create: `src/pixgen/optimization/models.py`
- Create: `src/pixgen/optimization/planner.py`
- Test: `tests/unit/optimization/test_variant_parser.py`
- Test: `tests/unit/optimization/test_models.py`

**Interfaces:**
- Consumes: `ErrorDetail` and `PixgenError` from Task 1.
- Produces: `OptimizeEngine`, `FormatChoice`, `ImageFormat`, `ResizeMode`, `VariantStatus`, `OptimizeStatus`, `VariantSpec`, `OptimizeRequest`, `SourceInfo`, `PlannedVariant`, `SkippedVariant`, `OptimizationPlan`, `EngineVariantResult`, `EngineBatchResult`, `VariantResult`, `OptimizeResult`, and `parse_variant(str) -> VariantSpec`.

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
    assert caught.value.detail.code is ErrorCode.INVALID_REQUEST
```

- [ ] **Step 2: Run the parser tests and verify they fail**

Run: `uv run pytest tests/unit/optimization/test_variant_parser.py tests/unit/optimization/test_models.py -v`

Expected: FAIL because the optimization package does not exist.

- [ ] **Step 3: Define the immutable domain models**

Use `ConfigDict(frozen=True)` for every request/plan/result model whose lifecycle is immutable. Define the exact core shapes:

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


class VariantStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class OptimizeStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class VariantSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    width: int | None
    height: int | None
    mode: ResizeMode


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    model_config = ConfigDict(frozen=True)
    path: Path
    format: ImageFormat
    width: int
    height: int
    orientation: int = 1
    byte_length: int
    has_alpha: bool
    has_icc_profile: bool


class PlannedVariant(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    model_config = ConfigDict(frozen=True)
    index: int
    name: str
    error: ErrorDetail


class OptimizationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    request: OptimizeRequest
    source: SourceInfo
    quality: int | None
    runnable: tuple[PlannedVariant, ...]
    skipped: tuple[SkippedVariant, ...]
    estimated_compressions_max: int | None = None


class VariantResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    status: VariantStatus
    path: Path | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    output_bytes: int | None = None
    error: ErrorDetail | None = None


class OptimizeResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: Literal[1] = 1
    operation: Literal["image.optimize"] = "image.optimize"
    engine: OptimizeEngine
    source: Path
    source_bytes: int
    status: OptimizeStatus
    requested: int
    completed: int
    skipped: int
    failed: int
    total_output_bytes: int
    estimated_compressions_max: int | None = None
    compression_count_this_month: int | None = None
    variants: tuple[VariantResult, ...]


class EngineVariantResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    completed: bool
    error: ErrorDetail | None = None


class EngineBatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    variants: tuple[EngineVariantResult, ...]
    compression_count_this_month: int | None = None
```

`ResizeMode.NONE` is internal for same-dimension optimization and is rejected by `parse_variant`. `FormatChoice.KEEP` is request-only; `PlannedVariant.output_format` is always a concrete `ImageFormat`. Results carry safe `ErrorDetail` objects, never exceptions or provider responses.

- [ ] **Step 4: Implement the strict parser**

Compile three anchored regular expressions for `WIDTHxHEIGHT`, `WIDTHw`, and `HEIGHTh`. Accept `scale` only with one dimension and `fit`, `cover`, or `thumb` only with both. Reject names outside `[a-z][a-z0-9-]*` and convert every parse failure to `PixgenError(ErrorCode.INVALID_REQUEST, "Invalid variant definition.", fields={"variant": expression})`.

- [ ] **Step 5: Run model and parser tests**

Run: `uv run pytest tests/unit/optimization/test_variant_parser.py tests/unit/optimization/test_models.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the domain contract**

```bash
git add src/pixgen/optimization tests/unit/optimization/test_variant_parser.py tests/unit/optimization/test_models.py
git commit -m "Define image optimization domain models"
```

### Task 3: Pure Planning, Source Inspection, and `--web`

**Files:**
- Create: `src/pixgen/config/paths.py`
- Modify: `src/pixgen/optimization/planner.py`
- Create: `tests/conftest.py`
- Test: `tests/unit/optimization/test_planner.py`
- Test: `tests/unit/optimization/test_source_inspection.py`

**Interfaces:**
- Consumes: models and `parse_variant` from Task 2; Pillow `Image` and `ImageOps`; PlatformDirs.
- Produces: `inspect_source(Path) -> SourceInfo`, `build_plan(OptimizeRequest, *, default_output_dir: Path | None = None) -> OptimizationPlan`, `default_artifact_dir() -> Path`, and constant `WEB_VARIANTS`.

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
    assert caught.value.detail.code is ErrorCode.INVALID_REQUEST
    assert not missing.exists()
```

- [ ] **Step 2: Add rotated, animated, decoded-format, and collision tests**

Create fixtures for an EXIF-orientation-6 JPEG, a two-frame GIF, an alpha PNG, and a JPEG renamed `.png`. Assert normalized dimensions, `has_alpha`, decoded format, static-image rejection, duplicate explicit-name rejection, local `thumb` rejection, Tinify explicit-quality rejection, `--output` multi-result rejection, output/output-dir mutual exclusion, canonical `.jpg` naming, all-skipped exit 2, missing-parent behavior, and no filesystem mutation under dry-run.

In `tests/conftest.py`, make `large_jpeg` a deterministic 2400x1600 RGB image and provide `small_jpeg`, `transparent_png`, `oriented_jpeg`, and `animated_gif`. Add a `run_pixgen` fixture that calls `[sys.executable, "-m", "pixgen", *args]` with captured text streams and an isolated environment. These fixtures are reused by later tasks.

- [ ] **Step 3: Run the planner tests and verify they fail**

Run: `uv run pytest tests/unit/optimization/test_planner.py tests/unit/optimization/test_source_inspection.py -v`

Expected: FAIL because `build_plan` and `inspect_source` do not exist.

- [ ] **Step 4: Implement safe source inspection**

`inspect_source` must resolve the path, require a regular file, open with Pillow, call `verify()`, reopen for metadata, reject `n_frames != 1`, map the decoded `Image.format` to the four supported formats, read EXIF orientation tag 274, compute dimensions after orientation, detect alpha from bands or transparency info, record byte length and ICC presence, and translate Pillow/decompression-bomb failures into safe `invalid_request` errors.

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

Merge explicit variants by replacing a preset name in place or appending a new name. Reject repeated explicit names. Compute output dimensions with `round()` and a lower bound of one pixel. `scale` skips when its requested axis exceeds the normalized source; `cover` and `thumb` skip when `max(target_width/source_width, target_height/source_height) > 1`; `fit` uses `min(1, width/source_width, height/source_height)` and therefore may produce an unchanged source-sized image.

- [ ] **Step 6: Implement formats, paths, and Tinify cost bounds**

Outside `--web`, default to `keep`; within `--web`, default to WebP and local quality 82. Reject explicit quality for Tinify and for PNG output. Resolve each destination to an absolute path, use `<source-stem>-<variant>.<extension>` with `.jpg`, `.png`, `.webp`, or `.avif`, and default to `default_artifact_dir()` when neither output option is present. Preflight every collision and parent before credentials; with `--mkdir`, validate the nearest existing ancestor without creating anything. For Tinify, calculate the conservative bound as one upload plus one unit per resize and one unit per conversion among runnable variants; set it to `None` for local plans.

- [ ] **Step 7: Run the planner suite**

Run: `uv run pytest tests/unit/optimization/test_planner.py tests/unit/optimization/test_source_inspection.py -v`

Expected: PASS, including the Review Focus alpha and rotated-dimension cases.

- [ ] **Step 8: Commit the planner**

```bash
git add src/pixgen/config/paths.py src/pixgen/optimization/planner.py tests/unit/optimization
git commit -m "Plan website image variants"
```

### Task 4: Batch Protocol and Atomic Runner

**Files:**
- Create: `src/pixgen/optimization/base.py`
- Create: `src/pixgen/optimization/runner.py`
- Test: `tests/unit/optimization/test_runner.py`
- Test: `tests/integration/test_atomic_optimization.py`

**Interfaces:**
- Consumes: `OptimizationPlan`, `EngineBatchResult`, `EngineVariantResult`, and Pillow.
- Produces: private `Optimizer` protocol and `execute_plan(plan: OptimizationPlan, optimizer: Optimizer) -> tuple[OptimizeResult, int]`.

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
            results.append(
                EngineVariantResult(name=variant.name, completed=True)
            )
        return EngineBatchResult(variants=tuple(results))


async def test_runner_returns_plan_order(web_plan) -> None:
    result, exit_code = await execute_plan(web_plan, FakeOptimizer())
    assert [item.name for item in result.variants] == [
        "thumbnail",
        "card",
        "content",
        "hero",
    ]
    assert exit_code == 0
```

- [ ] **Step 2: Write failing atomicity, metadata, and partial tests**

Test these concrete cases: a fake engine writes invalid dimensions; a fake engine writes an animated artifact; a fake engine writes EXIF/GPS; `os.replace` fails after an existing destination is present; one variant reports `optimization_failed`; and one planned variant is skipped. Assert no invalid artifact is promoted, the old destination bytes remain unchanged, temporary siblings are removed, successful siblings remain, plan order is stable, and error-code precedence produces 7 for artifact errors and 6 for ordinary skipped/optimization failures.

- [ ] **Step 3: Run the runner tests and verify they fail**

Run: `uv run pytest tests/unit/optimization/test_runner.py tests/integration/test_atomic_optimization.py -v`

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

`EngineVariantResult` contains only `name`, `completed: bool`, and an optional safe `ErrorDetail`. `EngineBatchResult` contains those ordered-or-unordered engine facts plus optional `compression_count_this_month`; file locations remain runner-owned.

- [ ] **Step 5: Implement staging and validation**

For each runnable destination, create a unique sibling name `.<filename>.pixgen-<uuid>.tmp`. Create allowed parents only after planning and only when `create_dirs` is true. Reopen every completed stage with Pillow; require one frame, the planned decoded format, exact expected dimensions, empty EXIF, no XMP keys, and no GPS. Flush and `os.fsync()` each complete staged file before `os.replace()`.

- [ ] **Step 6: Implement cleanup, aggregation, and exit precedence**

Always unlink remaining temporary files in `finally`. Merge engine results by variant name into plan order, insert planner skips at their original logical positions, sum only completed output bytes, and calculate top-level `success`, `partial`, or `failed`. Use error exit precedence `artifact/storage=7`, `timeout=5`, `credential/authentication=3`, `provider/network/rate-limit=4`, then partial/optimization/skipped=6; a fully completed batch is 0.

- [ ] **Step 7: Run the atomic runner tests**

Run: `uv run pytest tests/unit/optimization/test_runner.py tests/integration/test_atomic_optimization.py -v`

Expected: PASS, including preservation of the pre-existing destination and sibling successes.

- [ ] **Step 8: Commit the runner**

```bash
git add src/pixgen/optimization/base.py src/pixgen/optimization/runner.py tests/unit/optimization/test_runner.py tests/integration/test_atomic_optimization.py
git commit -m "Add atomic optimization runner"
```

### Task 5: Local Pillow Optimizer

**Files:**
- Create: `src/pixgen/optimization/local.py`
- Test: `tests/unit/optimization/test_local.py`
- Test: `tests/integration/test_local_optimization.py`

**Interfaces:**
- Consumes: private `Optimizer`, `OptimizationPlan`, and runner-owned staged paths.
- Produces: `LocalOptimizer.optimize(...) -> EngineBatchResult`.

- [ ] **Step 1: Write failing resize and one-decode tests**

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
    result, exit_code = await execute_plan(web_plan, LocalOptimizer())
    assert exit_code == 0
    assert opens == 1
    assert [(item.width, item.height) for item in result.variants] == [
        (400, 400),
        (1200, 630),
        (1280, 853),
        (1920, 1080),
    ]
```

Use a fixture whose proportions make the expected `round()` result unambiguous. Add tests for proportional width/height scale, contain-style `fit`, centered exact `cover`, and same-dimension `optimized` output.

- [ ] **Step 2: Write failing metadata and format tests**

For JPEG, PNG, WebP, and AVIF fixtures, assert output decodability and decoded format. Use an orientation-6 JPEG with EXIF/GPS/XMP and an ICC profile; assert pixels are upright, EXIF/GPS/XMP are absent, and the ICC profile survives where Pillow's encoder supports it. Assert `--web` uses quality 82 by spying on save keyword arguments and an explicit quality replaces it.

- [ ] **Step 3: Run the local tests and verify they fail**

Run: `uv run pytest tests/unit/optimization/test_local.py tests/integration/test_local_optimization.py -v`

Expected: FAIL because `LocalOptimizer` does not exist.

- [ ] **Step 4: Implement one-decode transformations**

Implement private `_load_source(path: Path) -> Image.Image`; it opens once, calls `load()`, applies `ImageOps.exif_transpose()`, copies the normalized image, closes the file handle, and returns the in-memory copy with source ICC bytes retained. Process variants sequentially. Use `Image.Resampling.LANCZOS`; use `resize()` for scale, `ImageOps.contain()` for fit, `ImageOps.fit(..., centering=(0.5, 0.5))` for cover, and `copy()` for internal `NONE`.

- [ ] **Step 5: Implement metadata-safe encoding**

Construct save keyword arguments from scratch so EXIF and XMP are never copied. Pass `icc_profile` only when present and supported. Convert non-alpha JPEG output to `RGB`; use `quality=plan.quality` and `optimize=True` for JPEG/WebP/AVIF when quality is set, and `optimize=True` for PNG. Catch each variant's decode/resize/encode exception, delete its stage, and return a safe `optimization_failed` for that variant while continuing the batch.

- [ ] **Step 6: Run the local engine and runner suites**

Run: `uv run pytest tests/unit/optimization/test_local.py tests/integration/test_local_optimization.py tests/unit/optimization/test_runner.py -v`

Expected: PASS.

- [ ] **Step 7: Commit the local engine**

```bash
git add src/pixgen/optimization/local.py tests/unit/optimization/test_local.py tests/integration/test_local_optimization.py
git commit -m "Optimize image variants locally"
```

### Task 6: Tinify Credentials and Single-Output HTTP Contract

**Files:**
- Create: `src/pixgen/credentials.py`
- Create: `src/pixgen/optimization/tinify.py`
- Test: `tests/unit/credentials/test_credentials.py`
- Test: `tests/providers/test_tinify.py`

**Interfaces:**
- Consumes: `OptimizationPlan`, HTTPX2 `AsyncClient`, `MockTransport`, and Pydantic `SecretStr`.
- Produces: `CredentialSource`, `ResolvedCredential`, `CredentialResolver.get("tinify")`, `CredentialResolver.source("tinify")`, `TinifyOptimizer`, and `_validate_output_url(str) -> httpx2.URL`.

- [ ] **Step 1: Write failing credential tests**

```python
def test_tinify_credential_prefers_keyring(monkeypatch, fake_keyring) -> None:
    fake_keyring.value = "keyring-secret"
    monkeypatch.setenv("TINIFY_API_KEY", "environment-secret")
    resolved = CredentialResolver(backend=fake_keyring).get("tinify")
    assert resolved.value.get_secret_value() == "keyring-secret"
    assert resolved.source is CredentialSource.KEYRING


def test_environment_fallback_survives_unavailable_keyring(
    monkeypatch, unavailable_keyring
) -> None:
    monkeypatch.setenv("TINIFY_API_KEY", "environment-secret")
    resolved = CredentialResolver(backend=unavailable_keyring).get("tinify")
    assert resolved.source is CredentialSource.ENVIRONMENT
```

Also assert missing credentials produce `credential_unavailable` exit 3 and neither secret appears in exception strings or serialized errors.

- [ ] **Step 2: Write failing HTTP upload, URL, and auth tests**

```python
async def test_same_size_tinify_uploads_once_and_downloads_once(
    tinify_plan, tmp_path
) -> None:
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

- [ ] **Step 3: Run credentials and Tinify tests and verify they fail**

Run: `uv run pytest tests/unit/credentials/test_credentials.py tests/providers/test_tinify.py -v`

Expected: FAIL because credentials and `TinifyOptimizer` do not exist.

- [ ] **Step 4: Implement Tinify credential resolution**

Use keyring service `pixgen`, account `tinify`, and fallback `TINIFY_API_KEY`. Inject a backend protocol exposing `get_password`, `set_password`, and `delete_password` so tests never touch the developer keychain. Catch `keyring.errors.KeyringError` only to permit environment fallback; never silently select an alternate backend.

- [ ] **Step 5: Implement upload and strict output URL validation**

Create an HTTPX2 `BasicAuth("api", secret)` and explicit `Timeout(connect=10, read=60, write=60, pool=10)`. `POST https://api.tinify.com/shrink` once with binary content. Accept only a `201` upload response. Validate the returned URL by parsed components: scheme `https`, host exactly `api.tinify.com`, port absent or 443, no username/password/query/fragment, and path matching `^/output/[A-Za-z0-9]+$` after rejecting encoded separators or dot segments.

- [ ] **Step 6: Implement same-size safe download and error translation**

For `ResizeMode.NONE` with unchanged format, stream one authenticated GET into the runner stage. Translate 401/403 to `authentication_failed`, 429 to `rate_limited`, 5xx/transport errors to `provider_unavailable`, and HTTPX2 timeouts to `timeout`. Use fixed safe messages and fields such as `{"operation": "upload"}`; discard response bodies and URLs. Do not retry any request in this task.

- [ ] **Step 7: Run the contract tests**

Run: `uv run pytest tests/unit/credentials/test_credentials.py tests/providers/test_tinify.py -v`

Expected: PASS, including the SSRF and secret-canary cases.

- [ ] **Step 8: Commit credentials and the base Tinify contract**

```bash
git add src/pixgen/credentials.py src/pixgen/optimization/tinify.py tests/unit/credentials tests/providers/test_tinify.py
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
- Produces: complete batch behavior with maximum concurrency four, ordered engine results, safe-GET retry, normalized oriented uploads, and conservative count capture.

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

Assert upload and derivative POST connection failures produce one attempt only. For the same-size GET, return 503 with `Retry-After: 1`, then a transport error, then success; inject a fake sleeper and zero jitter and assert three attempts and recorded delays. Make one derivative return 500 containing `secret-canary`; assert other files complete, the failed result is sanitized, plan order is retained, and runner exit is 4 because provider failure outranks generic partial exit 6.

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

- [ ] **Step 10: Commit the complete Tinify engine**

```bash
git add src/pixgen/optimization/tinify.py tests/providers/test_tinify.py tests/integration/test_tinify_batch.py tests/live/test_tinify_live.py
git commit -m "Add Tinify image variants"
```

### Task 8: `pixgen image optimize` CLI and Machine Contract

**Files:**
- Modify: `src/pixgen/cli/app.py`
- Create: `src/pixgen/cli/image.py`
- Modify: `src/pixgen/output.py`
- Test: `tests/cli/test_image_optimize.py`
- Test: `tests/cli/test_machine_output.py`
- Test: `tests/integration/test_optimize_subprocess.py`

**Interfaces:**
- Consumes: planner, `LocalOptimizer`, `TinifyOptimizer`, `CredentialResolver`, runner, and output helpers.
- Produces: `pixgen image optimize SOURCE` with the complete approved option contract and exact human/JSON stream behavior.

- [ ] **Step 1: Write failing help and local subprocess tests**

```python
def test_optimize_help_exposes_approved_options(run_pixgen) -> None:
    completed = run_pixgen("image", "optimize", "--help")
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
        "--quiet",
        "--no-color",
    ):
        assert option in completed.stdout


def test_web_local_subprocess_writes_four_variants(run_pixgen, large_jpeg, tmp_path):
    completed = run_pixgen(
        "image", "optimize", str(large_jpeg), "--web",
        "--output-dir", str(tmp_path), "--json",
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["operation"] == "image.optimize"
    assert [item["name"] for item in payload["variants"]] == [
        "thumbnail", "card", "content", "hero"
    ]
    assert completed.stderr == ""
```

- [ ] **Step 2: Write failing dry-run, partial, and stream tests**

Inject credential and client factories that fail if touched; run `--engine tinify --web --dry-run --mkdir` and assert one JSON plan, no keyring call, no network call, no directory. Assert skipped variants return exit 6 with completed files preserved, fatal validation emits one error envelope to stderr and nothing to stdout, `--quiet` suppresses successful human output, and `NO_COLOR` or `--no-color` removes ANSI sequences.

- [ ] **Step 3: Run CLI tests and verify failures**

Run: `uv run pytest tests/cli/test_image_optimize.py tests/cli/test_machine_output.py tests/integration/test_optimize_subprocess.py -v`

Expected: FAIL because the command is not registered.

- [ ] **Step 4: Declare the Cyclopts command exactly**

Create an async `optimize` command with positional `source: Path`, enum `--engine`, repeatable `--variant`, `--web`, `--format`, bounded `--quality`, `--output`, `--output-dir`, and booleans `--dry-run`, `--force`, `--mkdir`, `--json`, `--quiet`, and `--no-color`. Preserve `None` for omitted format and quality so the planner can distinguish explicit values from preset defaults.

- [ ] **Step 5: Compose only the selected engine after planning**

Call `build_plan` first. For dry-run, render the plan and return 0 when all planned outputs are runnable or 6 when it contains skips; do not construct a resolver or client. For local, construct only `LocalOptimizer`. For Tinify, resolve `tinify` only after planning, then create an HTTPX2 client with redirects disabled, pass it to `TinifyOptimizer`, and close it after `execute_plan`.

- [ ] **Step 6: Implement versioned JSON and human tables**

JSON success and partial results go to stdout as exactly one compact document. Fatal errors go to stderr as exactly one `ErrorEnvelope`. Human mode renders variant, status, dimensions, format, bytes, and absolute path, followed by source bytes, total output bytes, overall status, and Tinify monthly count when present. Report per-output byte savings, but never label source-to-total-output ratio as a compression percentage.

- [ ] **Step 7: Catch only safe boundaries**

Catch `PixgenError` and render its stable envelope. Convert any unexpected exception to `internal_error` without its `repr`, headers, URL, provider body, or secrets. Let Cyclopts usage failures use exit 2. Ensure partial results use the runner's category-aware exit code.

- [ ] **Step 8: Run CLI and subprocess tests**

Run: `uv run pytest tests/cli/test_image_optimize.py tests/cli/test_machine_output.py tests/integration/test_optimize_subprocess.py -v`

Expected: PASS.

- [ ] **Step 9: Commit the command**

```bash
git add src/pixgen/cli src/pixgen/output.py tests/cli tests/integration/test_optimize_subprocess.py
git commit -m "Add image optimize command"
```

### Task 9: Passive Info and Optional Tinify Doctor Check

**Files:**
- Create: `src/pixgen/cli/system.py`
- Modify: `src/pixgen/cli/app.py`
- Modify: `src/pixgen/optimization/tinify.py`
- Test: `tests/cli/test_info.py`
- Test: `tests/cli/test_doctor.py`

**Interfaces:**
- Consumes: Pillow feature registry, `CredentialResolver`, and injected HTTPX2 client.
- Produces: `collect_info(...) -> InfoResult`, `check_tinify_auth(...) -> DiagnosticCheck`, `pixgen info`, and `pixgen doctor [--tinify]`.

- [ ] **Step 1: Write failing passive-info tests**

Assert `info --json` reports Pixgen/Python/Pillow versions, actual local read/write capability for PNG/JPEG/WebP/AVIF, `tinify_included: true`, and Tinify credential presence/source without the value. Inject a network client that raises if called and assert no request or filesystem write occurs.

- [ ] **Step 2: Write failing doctor tests**

Cover these exact cases: no key and no `--tinify` yields a stable skipped check with no network; explicit `--tinify` with no key yields failed `credential_unavailable`; a configured key sends one empty `POST /shrink`; expected 400 client-data response is `ok`; 429 proves authentication but returns `warning`; 401/403 is failed authentication; transport and timeout failures use safe failed checks. Assert the secret and response body never appear.

- [ ] **Step 3: Run diagnostics tests and verify failures**

Run: `uv run pytest tests/cli/test_info.py tests/cli/test_doctor.py -v`

Expected: FAIL because diagnostics are not registered.

- [ ] **Step 4: Implement passive capability reporting**

Initialize Pillow's plugin registry, derive supported read/write formats from Pillow rather than hard-coding availability, and expose only presence and `keyring`/`environment` source for Tinify. Do not resolve the secret through the public info model.

- [ ] **Step 5: Implement the explicit Tinify auth probe**

Send exactly one authenticated empty-body `POST https://api.tinify.com/shrink`. Treat 400-class client-data errors other than 401/403 as proof the credential was accepted; make 429 a warning because it proves auth while reporting an account/rate condition. Never retry and never upload image bytes. Return stable IDs and `ok`, `warning`, `failed`, or `skipped` status.

- [ ] **Step 6: Register and render diagnostics**

Support human and schema-version-1 JSON for both commands. `doctor` runs Tinify only when a credential is configured or `--tinify` is explicit. Return 0 when checks are only ok/warning/skipped, 3 for missing/invalid credentials, 4 for provider/network failures, and 5 for timeout.

- [ ] **Step 7: Run diagnostics tests**

Run: `uv run pytest tests/cli/test_info.py tests/cli/test_doctor.py -v`

Expected: PASS with all network behavior supplied by `MockTransport`.

- [ ] **Step 8: Commit diagnostics**

```bash
git add src/pixgen/cli/system.py src/pixgen/cli/app.py src/pixgen/optimization/tinify.py tests/cli/test_info.py tests/cli/test_doctor.py
git commit -m "Diagnose image optimization engines"
```

### Task 10: Documentation, Agent Skill, Packaging, and Release Verification

**Files:**
- Modify: `README.md`
- Create: `docs/image-optimization.md`
- Create: `skills/pixgen/SKILL.md`
- Create: `skills/pixgen/references/image-optimization.md`
- Test: `tests/test_documented_commands.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: the final CLI and schema contracts.
- Produces: user documentation, provider-neutral agent instructions, command-smoke coverage, and a verified wheel.

- [ ] **Step 1: Write failing documentation and package tests**

```python
def test_documented_web_command_runs(run_pixgen, large_jpeg, tmp_path) -> None:
    completed = run_pixgen(
        "image", "optimize", str(large_jpeg), "--web",
        "--output-dir", str(tmp_path), "--json",
    )
    assert completed.returncode == 0


def test_agent_skill_references_stable_json_contract() -> None:
    skill = Path("skills/pixgen/SKILL.md").read_text()
    reference = Path("skills/pixgen/references/image-optimization.md").read_text()
    assert "pixgen image optimize" in skill
    assert "optimization_failed" in reference
    assert "TINIFY_API_KEY" in reference
```

Add a package test that builds a wheel, creates an isolated environment, invokes `pixgen image optimize --help`, and imports Pillow, HTTPX2, and `pixgen.optimization` from the installed wheel rather than the source checkout.

- [ ] **Step 2: Run the documentation/package tests and verify failures**

Run: `uv run pytest tests/test_documented_commands.py tests/test_package.py -v`

Expected: FAIL because the docs and skill do not exist yet.

- [ ] **Step 3: Write user documentation**

Document local same-size optimization, custom scale/fit/cover variants, the four exact `--web` outputs, explicit Tinify `thumb`, format/quality rules, no-upscale skips, partial exit 6, force/create-dir behavior, dry-run cost bounds, keyring plus `TINIFY_API_KEY`, metadata removal, Tinify upload privacy, and current billing links. State that prices can change and the returned compression count is authoritative.

- [ ] **Step 4: Write the provider-neutral Agent Skill**

Teach agents to prefer local mode, use `--json`, inspect dry-run output, select Tinify only when remote upload and billing are acceptable, retain successful paths on partial exit 6, branch on stable error codes, and run `pixgen doctor --tinify --json` for Tinify setup failures. Keep raw HTTP payloads, provider URLs, and direct SDK instructions out of the skill.

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

Expected: PASS, including dependency security and Bandit.

- [ ] **Step 7: Build and smoke-test the installed wheel**

Run: `uv build`

Expected: source distribution and wheel created successfully.

Run: `uv run --isolated --with ./dist/pixgen-0.1.0-py3-none-any.whl pixgen image optimize --help`

Expected: exit 0 and the complete optimization option list.

- [ ] **Step 8: Optionally run the billable live smoke test only with explicit approval**

Run: `PIXGEN_RUN_LIVE_TINIFY=1 uv run pytest -m live_tinify tests/live/test_tinify_live.py -v`

Expected: PASS and consume Tinify quota. Do not run this step without a configured test key and explicit confirmation for that billable request.

- [ ] **Step 9: Commit documentation and release verification**

```bash
git add README.md docs/image-optimization.md skills/pixgen tests/test_documented_commands.py tests/test_package.py
git commit -m "Document image optimization workflows"
```

- [ ] **Step 10: Request final code review**

Use `superpowers:requesting-code-review` to review the complete branch against `docs/superpowers/specs/2026-09-19-image-optimization-design.md`, this implementation plan, the stable machine schema, paid-request retry policy, secret handling, and atomic artifact guarantees. Resolve findings, rerun Steps 5-7, and then use `superpowers:finishing-a-development-branch` for the integration decision.
