# Pillow Image Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `pixgen optimize SOURCE` command for local Pillow resizing and compression, including the website preset.

**Architecture:** Keep CLI parsing and output rendering in `cli/`, planning and execution in a small `optimization/` package, and reusable pixel/codec operations in `images/transform.py`. Reuse existing Pixgen errors, result envelopes, settings, and atomic artifact writes; do not add a remote optimizer abstraction.

**Tech Stack:** Python 3.14, Cyclopts, Pydantic 2, Pillow (already installed), Rich, pytest, Ruff, Pyrefly.

**Spec:** `docs/superpowers/specs/2026-10-08-pillow-image-optimization-design.md`

## Global Constraints

- During implementation, use Context7 for current library documentation and verify API choices against the official upstream docs/release notes. Resolve the Context7 library ID before querying; research the APIs being used, not just package-level overviews.
- Check the repository's resolved versions in `uv.lock` and compatibility ranges in `pyproject.toml`. Use current documentation to confirm best practices, but implement only APIs supported by the resolved project version; treat a needed dependency upgrade as a separate design decision.
- Record the official documentation links, version checked, and any consequential API choices in the task/PR notes. If Context7 and official docs disagree, or docs require a version change or scope change, pause and report the discrepancy before implementing that part.
- Pillow is the only v1 processing engine; do not add dependencies for optimization.
- The command is standalone and explicit: generation and provider upload flows never invoke it.
- Support static PNG, JPEG, WebP, and AVIF only when the installed Pillow build supports the required input/output format.
- Custom size flags are repeatable named options: `--fit WIDTHxHEIGHT`, `--cover WIDTHxHEIGHT`, `--width PIXELS`, and `--height PIXELS`; do not introduce packed `name=size:mode` syntax.
- Dry-run results use `planned` variant states and never claim files were written; valid skip-only executions return success.
- Never upscale; never modify the source; never write during dry-run.
- Use `pixgen.artifacts.write_atomic` for final output promotion and preserve existing destinations unless `--force` is set.
- Reuse `ErrorCode`, `PublicError`, `ExitStatus`, and schema version `"1"`; do not create a parallel CLI error system.
- Shared image transforms must make colour/profile policy explicit so media sanitisation can convert to sRGB and strip ICC while optimization can preserve ICC when supported.
- Do not add Tinify, HTTP clients, credentials, network tests, keyring support, persistence, or automatic optimization hooks.
- Follow the repository's Python style, frozen Pydantic model conventions, British English docstrings, and TDD workflow. Tests use local fixtures and never require network access or real credentials.

## Review Focus

- An EXIF-oriented image must use its transposed dimensions for planning and output, and an animated input must be rejected instead of silently processing only its first frame; pin in Task 1 and Task 3 tests.
- Corrupt pixel payloads may pass header-only dry-run inspection but must fail execution before the affected destination is written; pin in Task 3 and Task 4 tests.
- A transparent image requested as JPEG must be rejected before any output directory or file is created; pin in Task 3 tests.
- Small-source width/height variants and aspect-ratio cover crops that require enlargement must be skipped without upscaling, while valid sibling variants still complete; pin in Task 3 and Task 4 tests.
- Repeated custom size options must produce deterministic names and result order, with duplicate transforms and output collisions rejected; pin in Task 3 tests.

---

## File Map

### Shared image processing

- Modify `src/pixgen/images/inspect.py` and `src/pixgen/images/mime.py` to recognise the supported static formats based on the installed Pillow capabilities while retaining existing input size and corruption checks.
- Create `src/pixgen/images/transform.py` for orientation-normalised decode, resize/crop, clean metadata encoding, and explicit colour/profile policy. This is the shared image codec surface for future `media` commands.
- Create `tests/images/test_transform.py` and extend `tests/images/test_inspect.py` for formats and inspection behavior.

### Public optimization result and core behavior

- Modify `src/pixgen/core/errors.py`, `src/pixgen/core/results.py`, `src/pixgen/cli/outcome.py`, and `src/pixgen/cli/render.py` to extend current result/error/render contracts.
- Create `src/pixgen/optimization/__init__.py`, `models.py`, `planner.py`, and `application.py` for request, plan, per-variant results, path preflight, and sequential local execution.
- Create matching tests under `tests/optimization/` and extend core/CLI contract tests.

### CLI, runtime, and user documentation

- Create `src/pixgen/cli/optimize.py`; modify `src/pixgen/cli/app.py` and `src/pixgen/runtime.py` to wire the local application without constructing any provider client for optimization.
- Create `tests/cli/test_optimize.py`, extend `tests/cli/test_app.py` and `tests/test_runtime.py`, and add `tests/optimization/test_application.py`.
- Create `docs/image-optimization.md` and update `README.md` with the explicit Pillow-only command and `--web` shortcut. No Pixgen agent skill currently exists in the repository, so do not create one as part of this feature.

---

### Task 1: Add shared Pillow transform primitives

**Files:**
- Modify: `src/pixgen/images/inspect.py`
- Modify: `src/pixgen/images/mime.py`
- Create: `src/pixgen/images/transform.py`
- Test: `tests/images/test_inspect.py`
- Test: `tests/images/test_transform.py`

**Interfaces:**
- Produces `ColourProfilePolicy` (`PRESERVE`, `CONVERT_SRGB_AND_STRIP`), `ResizeOperation` (`FIT`, `COVER`, `WIDTH`, `HEIGHT`), `DecodedImage`, `ImageTransformError`, `load_normalized(content: bytes, *, policy: ColourProfilePolicy) -> DecodedImage`, `resize_pixels(source: DecodedImage, *, operation: ResizeOperation, width: int | None = None, height: int | None = None) -> Image.Image`, and `encode_clean(image: Image.Image, *, output_format: str, quality: int | None, icc_profile: bytes | None) -> bytes`.
- `DecodedImage` carries oriented pixels, source format, original oriented width/height, and ICC bytes only when policy preserves them. `images/transform.py` has no CLI, preset, settings, or output-path knowledge.
- Existing `load_image(path)` remains the validated byte-loading boundary; add AVIF MIME mapping and read/encode capability checks without making unavailable formats appear supported.

- [ ] **Step 1: Add failing tests for normalized image loading and transforms**

Test EXIF transpose and dimensions, animated input rejection, fit bounds, exact centered cover crop, width/height proportional scale, metadata-free fresh encoding, ICC preservation versus conversion/stripping policies, supported format round trips, and corruption errors. Use Pillow-created in-memory images; avoid committed binary fixtures.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/images/test_inspect.py tests/images/test_transform.py -v`
Expected: FAIL because the shared transform module and format capability behavior do not exist.

- [ ] **Step 3: Research the current Pillow APIs**

Use Context7 to resolve the Pillow library ID, then query current official documentation for `ImageOps.exif_transpose`, `ImageOps.contain`/`ImageOps.fit`, `ImageCms` profile conversion, clean encoder metadata, and AVIF read/write capability detection. Cross-check the official Pillow handbook and release notes against the Pillow version in `uv.lock`; record the documentation links and selected APIs in the implementation notes. If a desired API is unavailable in the locked version, pause before adding or upgrading a dependency.

- [ ] **Step 4: Implement the shared transform API**

Apply EXIF orientation before exposing dimensions. Use `ImageOps.contain` for fit and `ImageOps.fit` for centered cover. For colour conversion, use the source ICC profile when present and produce sRGB pixels; when stripping, return no source profile for encoding. Build fresh encoder kwargs so EXIF, XMP, and GPS data are not copied.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run: `uv run pytest tests/images/test_inspect.py tests/images/test_transform.py -v`
Expected: PASS, including skip-free transform-level format round trips for each available encoder.

- [ ] **Step 6: Commit**

```bash
git add src/pixgen/images/inspect.py src/pixgen/images/mime.py src/pixgen/images/transform.py tests/images/test_inspect.py tests/images/test_transform.py
git commit -m "Add shared local image transforms"
```

### Task 2: Add optimization result and CLI outcome contracts

**Files:**
- Modify: `src/pixgen/core/errors.py`
- Modify: `src/pixgen/core/results.py`
- Modify: `src/pixgen/cli/outcome.py`
- Modify: `src/pixgen/cli/render.py`
- Test: `tests/core/test_errors.py`
- Test: `tests/core/test_results.py`
- Test: `tests/cli/test_outcome.py`
- Test: `tests/cli/test_render.py`

**Interfaces:**
- Produces `ErrorCode.OPTIMIZATION_FAILED`, `VariantStatus` (`PLANNED`, `COMPLETED`, `SKIPPED`, `FAILED`), `OptimizeVariantResult`, and `OptimizeResult` with `schema_version: Literal["1"]`, a UUID run ID, source path, `dry_run: bool`, ordered variants, and optional command-level `PublicError`.
- Each variant includes a stable name and status. `PLANNED` and `COMPLETED` require output path, format, width, and height; `COMPLETED` additionally requires output byte count. `SKIPPED` requires a reason and has no output path. `FAILED` requires `PublicError` and has no output path. Enforce these mutually exclusive states in Pydantic validators.
- Extends `PublicResult`, `exit_status`, and `render_outcome`; adds `render_optimize_result` with JSON on stdout and concise human output with failures/warnings on stderr.

- [ ] **Step 1: Write failing tests for result invariants and statuses**

Assert a result requires either command-level error or a non-empty ordered variant tuple; planned/completed/skipped/failed variants require exactly their corresponding fields. Planned variants contain resolved output metadata but no output byte count. Assert exit `0` for dry-run, completed, and skip-only results; `2` for command-level rejection; `3` when every executed variant fails; and `4` for mixed completed/failed variants. Assert schema version is the string `"1"`.

Skipped variants do not count as attempted: if every attempted variant fails and the remainder are skipped, the run is still `ALL_FAILED` (`3`).

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `uv run pytest tests/core/test_errors.py tests/core/test_results.py tests/cli/test_outcome.py tests/cli/test_render.py -v`
Expected: FAIL because optimization results and error mapping do not exist.

- [ ] **Step 3: Check Pydantic result-model guidance**

Use Context7 to resolve and query the official Pydantic documentation for frozen models and `model_validator(mode="after")`. Verify those patterns against the project's declared/resolved Pydantic version and existing local result models; note the official docs/version checked.

- [ ] **Step 4: Implement the result and rendering contracts**

Use frozen `BaseModel` records with `extra="forbid"`. Match existing `PublicError` and `CliOutcome` behavior; keep result order as supplied by the plan. Human rendering must not print a success line for failed variants as if their files existed.

- [ ] **Step 5: Rerun focused tests**

Run: `uv run pytest tests/core/test_errors.py tests/core/test_results.py tests/cli/test_outcome.py tests/cli/test_render.py -v`
Expected: PASS for model invariants, JSON, human output, and exit mapping.

- [ ] **Step 6: Commit**

```bash
git add src/pixgen/core/errors.py src/pixgen/core/results.py src/pixgen/cli/outcome.py src/pixgen/cli/render.py tests/core/test_errors.py tests/core/test_results.py tests/cli/test_outcome.py tests/cli/test_render.py
git commit -m "Add image optimization result contracts"
```

### Task 3: Implement pure optimization planning and output preflight

**Files:**
- Create: `src/pixgen/optimization/__init__.py`
- Create: `src/pixgen/optimization/models.py`
- Create: `src/pixgen/optimization/planner.py`
- Test: `tests/optimization/__init__.py`
- Test: `tests/optimization/test_planner.py`

**Interfaces:**
- Produces frozen `OptimizeRequest`, `ResizeSpec`, `PlannedVariant`, and `OptimizePlan` types plus `build_plan(request: OptimizeRequest, *, default_output_dir: Path | None = None) -> OptimizePlan`.
- `OutputFormat` is a `StrEnum` with `KEEP`, `JPEG`, `PNG`, `WEBP`, and `AVIF`. `OptimizeRequest` stores the source path; `web`; ordered tuples of raw `fit`, `cover`, `width`, and `height` values; optional format override; quality; output/output-dir; `dry_run`; `mkdir`; and `force`.
- `ResizeSpec` stores `name`, `operation`, optional `width`, and optional `height`, requiring both for `FIT`/`COVER` and exactly one for `WIDTH`/`HEIGHT`. `OptimizePlan` stores validated source bytes/facts, selected format/quality, ordered runnable and skipped variants, and resolved absolute destinations. It does not write files or create directories.
- The planner consumes `load_image` plus header metadata and Pillow capability information. Invalid format, malformed dimensions, unsupported encoder, invalid quality, alpha-to-JPEG, invalid output combinations, duplicate targets, and collisions raise `PixgenError(ErrorCode.INVALID_REQUEST, ...)` before execution.

- [ ] **Step 1: Write failing planner tests**

Cover the default same-dimension output; exact web preset and order; repeated `--fit`, `--cover`, `--width`, and `--height` expansion and derived names; mixed `--web` plus custom ordering; `--format`/`--quality` overrides; duplicate target rejection; EXIF-oriented dimensions; fit bounds; width/height and aspect-ratio cover no-upscale skips; valid skip-only plans; unsupported runtime formats; animated image rejection; transparent-to-JPEG rejection; output paths resolving to the source; default/explicit output paths; `--output` single-result restriction; `--output`/`--output-dir` mutual exclusion; existing collisions with and without `force`; and prove dry-run planning creates no directory or file.

- [ ] **Step 2: Run planner tests and verify they fail**

Run: `uv run pytest tests/optimization/test_planner.py -v`
Expected: FAIL because optimization request, plan, and planner types do not exist.

- [ ] **Step 3: Implement `build_plan` and request models**

Parse each dimension option as a positive integer or `WIDTHxHEIGHT`; do not accept colon/equal-delimited name-size-mode strings. Apply deterministic order: website variants first, then `fit`, `cover`, `width`, `height`, preserving value order within each flag. Use semantic website names and operation/dimension-derived custom names. An absent format override resolves to WebP for `--web` and `keep` otherwise; an explicit format overrides that choice. An absent quality resolves to 82 for `--web` and Pillow defaults otherwise. Resolve `keep` to the source format and check the actual output encoder capability. For default output directory selection use `default_output_dir` or `Path.cwd() / "pixgen"`; do not call `mkdir` while planning. Reject any resolved output path that points to the input source.

- [ ] **Step 4: Run planner tests and verify they pass**

Run: `uv run pytest tests/optimization/test_planner.py -v`
Expected: PASS; dry-run plans have no filesystem side effects.

- [ ] **Step 5: Commit**

```bash
git add src/pixgen/optimization/__init__.py src/pixgen/optimization/models.py src/pixgen/optimization/planner.py tests/optimization/__init__.py tests/optimization/test_planner.py
git commit -m "Plan local image optimization outputs"
```

### Task 4: Execute local variants and atomically publish results

**Files:**
- Create: `src/pixgen/optimization/application.py`
- Test: `tests/optimization/test_application.py`

**Interfaces:**
- Produces `OptimizeApplication(settings: Settings)` and synchronous `run(self, request: OptimizeRequest) -> OptimizeResult`. Use `settings.generation.output_dir` as the configured output-directory default.
- `run` obtains an `OptimizePlan`; for dry-run it returns `dry_run=True` with `PLANNED` variants and no filesystem changes. During execution it calls `load_normalized(..., policy=ColourProfilePolicy.PRESERVE)` once, processes runnable variants sequentially, verifies each encoded output by reopening it, and calls `write_atomic(path, data, overwrite=request.force)` only after that variant is complete.
- Source decode failure becomes a command-level `INVALID_REQUEST`; a variant resize/encode failure becomes `OPTIMIZATION_FAILED`; a failed atomic write becomes `ARTIFACT_FAILURE`. One variant failure is captured as a failed `OptimizeVariantResult`; other variants continue. A command-level planning error becomes `OptimizeResult(error=...)`. Successful outputs remain published if a later variant fails.

- [ ] **Step 1: Write failing execution tests**

Use local PNG/JPEG/WebP fixtures and `tmp_path` to assert actual dimensions/formats, EXIF and GPS removal, ICC preservation where supported, `PLANNED` dry-run states with no directories, `--mkdir` behavior, no overwrite without `force`, atomic replacement with `force`, output verification, sequential ordered results, corrupt payload failure before write, and a simulated per-variant encode/write failure that preserves successful siblings and reports partial failure.

- [ ] **Step 2: Run execution tests and verify they fail**

Run: `uv run pytest tests/optimization/test_application.py -v`
Expected: FAIL because there is no optimization application.

- [ ] **Step 3: Implement `OptimizeApplication.run`**

Create directories only during execution and only where request policy permits. Catch source decode errors before entering the variant loop, then catch known per-variant transform and artifact errors at the variant boundary; do not swallow unexpected programming exceptions. A valid skip-only run returns success; all attempted variants failed maps to exit `3`; mixed completion/failure maps to `4`.

- [ ] **Step 4: Run execution tests and verify they pass**

Run: `uv run pytest tests/optimization/test_application.py -v`
Expected: PASS; the source remains unchanged and temporary/partial files are not exposed as successful outputs.

- [ ] **Step 5: Commit**

```bash
git add src/pixgen/optimization/application.py tests/optimization/test_application.py
git commit -m "Execute local image optimization plans"
```

### Task 5: Wire `pixgen optimize` into the root CLI and runtime

**Files:**
- Create: `src/pixgen/cli/optimize.py`
- Modify: `src/pixgen/cli/app.py`
- Modify: `src/pixgen/runtime.py`
- Test: `tests/cli/test_optimize.py`
- Test: `tests/cli/test_app.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- `build_optimize_app(application: OptimizeApplication) -> App` defines `optimize(source: Path, *, web: bool, fit: list[str] | None, cover: list[str] | None, width: list[int] | None, height: list[int] | None, format: OutputFormat | None, quality: int | None, output: Path | None, output_dir: Path | None, dry_run: bool, mkdir: bool, force: bool, json: bool) -> CliOutcome`.
- Add the optimization application to `Runtime` and pass it into `build_app`; register `optimize` as a root command alongside `create`, `edit`, `model`, and `group`.
- Use `cli_command(optimize_error)` so command-level failures render an `OptimizeResult`; provider clients are not used by this command.

- [ ] **Step 1: Write failing CLI and runtime tests**

Assert Cyclopts parses a positional source, repeatable `--fit`/`--cover`/`--width`/`--height`, and normal format/quality/output flags. Assert packed `--variant NAME=...:...` is not accepted. Exercise `optimize --help`, `--json`, `--dry-run` planned states, and exit codes through a fake application. Assert `build_runtime` creates the local optimization application without constructing HTTP or Gemini clients.

- [ ] **Step 2: Run focused CLI/runtime tests and verify they fail**

Run: `uv run pytest tests/cli/test_optimize.py tests/cli/test_app.py tests/test_runtime.py -v`
Expected: FAIL because `optimize` is not registered and runtime does not expose its application.

- [ ] **Step 3: Check Cyclopts command and repeated-option guidance**

Use Context7 to resolve and query the official Cyclopts documentation for command registration, positional `Path` parameters, repeatable `list` options, and `StrEnum` choices. Compare with the CLI patterns on the current `main` branch and the version in `uv.lock`; record the official documentation/version checked before selecting implementation details.

- [ ] **Step 4: Implement CLI parsing and composition wiring**

Mirror existing root command patterns in `cli/image.py` and `cli/group.py`: one `App`, ordinary named options, repeatable list-valued flags, `cli_command`, and a returned `CliOutcome`. Construct no provider-specific client or additional settings secret.

- [ ] **Step 5: Run focused CLI/runtime tests and verify they pass**

Run: `uv run pytest tests/cli/test_optimize.py tests/cli/test_app.py tests/test_runtime.py -v`
Expected: PASS, including unsupported packed syntax and no provider client construction.

- [ ] **Step 6: Commit**

```bash
git add src/pixgen/cli/optimize.py src/pixgen/cli/app.py src/pixgen/runtime.py tests/cli/test_optimize.py tests/cli/test_app.py tests/test_runtime.py
git commit -m "Add the optimize CLI command"
```

### Task 6: Document and verify the Pillow-only workflow

**Files:**
- Create: `docs/image-optimization.md`
- Modify: `README.md`

**Interfaces:**
- Documents exact command syntax, default behavior, `--web`, repeated custom size options, output naming, formats and quality, no-upscale skips, dry-run, `--mkdir`, `--force`, result statuses, and local-only privacy behavior.
- Explicitly states that Pixgen does not optimize generated images or provider uploads automatically and that Tinify is not included.

- [ ] **Step 1: Write the user documentation**

Include concise examples for a same-format optimize, one custom resize, multiple same-operation sizes, website variants, dry-run, and safe overwrite. Do not document remote service comparisons as features of this command.

- [ ] **Step 2: Review the docs for syntax and validate the full project**

Run: `git diff --check`, then `just lint && just type-check && just test`.
Expected: all selected checks pass. Do not add network-dependent or billable tests.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/image-optimization.md
git commit -m "Document local image optimization"
```

## Final Review

- Confirm every requirement in the approved design has a task, especially dry-run side-effect freedom, metadata policy, no-upscale behavior, partial failures, `--web` defaults, and current CLI result contracts.
- Confirm the media plan can consume `images/transform.py` directly and does not introduce a parallel decode/encode implementation or inherit optimization's ICC policy.
- Use a fresh reviewer to check the finished branch against the spec and this plan before considering integration; do not add Tinify or automatic optimization as follow-up scope.
