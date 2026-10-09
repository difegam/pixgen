# Media sanitization and publishing commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Revision note (2026-09-30):** Reviewed and updated against the current `main` branch and against `docs/superpowers/plans/2026-09-19-image-optimization.md`, which was updated the same day. Three things were wrong or missing in the original draft: (1) the tech stack cited an "existing `filetype`" dependency that does not exist anywhere in the repo; (2) research confirmed Pillow alone cannot write XMP for JPEG or PNG (only WebP), so the public-metadata writer in Task 4 needs a real dependency, not "Pillow ... using an explicit metadata-free encoder configuration"; (3) the plan's own spec says "The media layer should not add a second image codec pipeline," but Task 3 built an independent decode/normalize/encode pipeline (`media/transform.py`) with no link to the optimization plan's equivalent (`optimization/local.py`). See "What changed since the original draft" below.

**Goal:** Add image-only `media inspect`, `media sanitize`, and `media publish` commands, plus automatic private/provider preparation for image uploads.

**Architecture:** Build one local image pipeline for inspection, pixel normalization, metadata removal, standards-based public metadata writing, verification, and atomic promotion. Keep CLI parsing and rendering at the edge, keep policy/result models in `media`, and invoke ingress preparation from `ImageApplication` before provider requests. Reuse `pixgen.artifacts.write_atomic` for final promotion and share decode/normalize/encode primitives with the image-optimization plan's local engine instead of building a second codec pipeline.

**Tech Stack:** Python 3.14, Pydantic frozen models, Pillow for local decode/transform/encode, **`pyexiv2`** for reading and writing IPTC/XMP metadata (new dependency — see below), Cyclopts, Rich, pytest, Pyrefly, Ruff, and Pixgen's atomic artifact writer.

**Spec:** `docs/superpowers/specs/2026-09-27-media-commands-design.md` — still accurate on policy/product decisions (metadata allowlist, provenance rules, C2PA deferral); this plan corrects only implementation-level facts that have drifted or were wrong.

### What changed since the original draft

- **No `filetype` dependency exists**, and it was never needed: `pixgen.images.inspect.load_image` already decode-verifies format via Pillow (`_FORMAT_TO_MEDIA_TYPE`). Media inspection reuses that, not a new library.
- **Pillow cannot write XMP for JPEG or PNG** — confirmed via research. `Image.save(xmp=...)` only works for WebP; Pillow can *read* XMP (`Image.getxmp()`) but has no IPTC IIM support at all. Writing the Task 4 metadata allowlist (Credit Line, Copyright Notice, WebStatement, Licensor URL, IPTC 2025.1 AI-provenance fields) needs a real metadata-writing dependency. **Add `pyexiv2`** (wraps libexiv2; actively maintained, wheels available, reads/writes EXIF/IPTC/XMP across JPEG/PNG/WebP). It is also the more reliable tool for Task 2's IPTC/XMP *presence* inspection, since Pillow has no IPTC IIM reader.
- **C2PA tooling exists now** (`c2pa-python`, actively maintained, official bindings) — noted for the record, but the plan's decision to defer C2PA support stays correct; this is scope, not a blocker.
- **Error/result contract:** this plan already anticipated the app's real `PublicError`/`ErrorCode` shape reasonably well, unlike the optimization plan's original draft. It still needs concrete wiring: reuse `pixgen.core.errors.ErrorCode` (add one new member, `MEDIA_VERIFICATION_FAILED`, instead of a separate `MediaErrorCode` type) and define `MediaResult` in `media/models.py` as a single-outcome result (no partial-success states, matching the spec), added to `pixgen.cli.outcome`'s `PublicResult` union. Its exit-status handling needs **no new branch** in `exit_status` — the existing `if result.error is not None: return ExitStatus.REJECTED` / fallthrough `ExitStatus.SUCCESS` behaviour already covers a single-outcome result correctly, same as `ModelGetResult`.
- **Codec duplication with the optimization plan:** Task 3's `transform.normalize_pixels`/decode/encode logic is the same one-decode-then-EXIF-transpose-then-encode path as `optimization/local.py`'s `_load_source`/encode step in the sibling plan. Whichever plan is implemented first should land the shared primitives; the plan implemented second imports them instead of rewriting them. This plan's Task 3 below assumes the shared primitives may not exist yet and specifies both orders.
- **Runtime wiring:** `src/pixgen/runtime.py`'s `Runtime` dataclass currently only carries `application`, `registry`, `settings`, `cli_factories`. Task 5 needs to add a `media_application` field there and thread it through `cli/app.py`'s `build_app`, matching how `ImageApplication` is already constructed and passed in.
- **No `tests/media/`, `tests/integration/`, or subprocess-CLI test helper exist yet** — all net new, same as the optimization plan's testing gaps. Coordinate fixture/helper names if both plans are implemented close together to avoid two incompatible `run_pixgen` helpers.

## Global Constraints

- Support one static PNG, JPEG, or WebP image per media command in v1.
- Never modify the source file.
- Never upload the source file when `media.uploads.sanitize = true`.
- Private outputs always normalize orientation and sRGB, remove source metadata and C2PA, and re-encode.
- Public outputs write only configured rights/provenance metadata, via `pyexiv2` for JPEG/PNG and Pillow's native `xmp=` for WebP.
- Do not infer AI authorship from pixels, filenames, or weak metadata.
- Prompt and prompt-writer metadata are disabled by default.
- `media.c2pa.enabled = true` fails until signing and verification are implemented — no `c2pa-python` dependency is added by this plan.
- Provider preparation downsizes only when needed and does not expose provider-specific tuning flags in v1.
- Use `uv run pytest`, `uv run pyrefly check`, and `just lint`; the type checker is Pyrefly, not mypy.
- Use British English in docstrings, Google-style docstrings, frozen Pydantic models (`ConfigDict(frozen=True, extra="forbid")`, matching every existing model in `pixgen.core`/`pixgen.config`), and `from __future__ import annotations` in production Python modules.
- Do not make real network requests or use real credentials in tests.
- `sanitize`/`publish` are single-outcome commands: `MediaResult` carries either a successful artifact or one `PublicError`, never a partial batch — do not reuse `CommandResult`/`TargetResult`, which are shaped for multi-target (model × variant) generation runs.

## Review Focus

- JPEG EXIF orientation with GPS metadata: pixels must rotate correctly while all source metadata disappears. Test in Task 3.
- PNG ancillary chunks and WebP XMP/EXIF: private outputs must not retain metadata through a format-specific side channel. Test in Task 3.
- Transparent image published as JPEG: reject before writing or changing the source. Test in Task 4.
- An arbitrary local image with AI-looking text or weak metadata: do not invent an AI provenance claim. Test in Task 4.
- Oversized provider input with multiple references: sanitize once per source, downscale only the oversized prepared copy, and upload no original bytes. Test in Task 6.
- `pyexiv2` writes exactly the configured allowlist and nothing else: a source image with arbitrary IPTC/XMP fields published with only `credit_line` set must yield an output containing that one field and no trace of the source's other fields. Test in Task 4.

### Task 1: Add media policy models, configuration, and error/result contracts

**Files:**
- Create: `src/pixgen/media/__init__.py`
- Create: `src/pixgen/media/models.py`
- Modify: `src/pixgen/config/models.py`
- Modify: `src/pixgen/core/errors.py`
- Modify: `src/pixgen/cli/outcome.py`
- Modify: `src/pixgen/cli/render.py`
- Test: `tests/media/test_models.py`
- Test: `tests/config/test_models.py`
- Test: `tests/core/test_errors.py`
- Test: `tests/cli/test_outcome.py`

**Interfaces:**
- Produces frozen policy models `UploadSettings`, `SanitizeSettings`, `PublishSettings`, `MetadataSettings`, `ProvenanceSettings`, and `C2PASettings` under a frozen `MediaSettings` model, following the same `ConfigDict(frozen=True, extra="forbid")` style as `GenerationSettings`.
- Produces `MediaFormat`, `MetadataCategory`, `DigitalSourceType`, `ImageInspection`, `MediaTransformReport`, and `MediaResult` in `media/models.py`.
- Adds `ErrorCode.MEDIA_VERIFICATION_FAILED` to the existing `ErrorCode` enum (no separate `MediaErrorCode` type — unsupported-format/policy rejections reuse the existing `ErrorCode.INVALID_REQUEST`, and atomic-write failures reuse `ErrorCode.ARTIFACT_FAILURE`, matching how the codebase already reuses one shared enum everywhere else).
- `Settings.media` exposes `MediaSettings` with the exact defaults from the spec's `[media.*]` TOML tables.
- Adds `MediaResult` to `pixgen.cli.outcome`'s `type PublicResult = CommandResult | ModelGetResult | ModelListResult | OptimizeResult | MediaResult` union (the `OptimizeResult` member only exists if the image-optimization plan has landed first; if not, add just `MediaResult`) and `render_media_result` to `cli/render.py`.

- [ ] **Step 1: Write failing model and configuration tests**

  Pin defaults, frozen/extra-forbid behaviour, valid quality and dimension ranges, `format = null`, URL validation, enum values, and rejection of `c2pa.enabled = true` until signing support exists. Add a `cli/test_outcome.py` case asserting `exit_status` returns `ExitStatus.SUCCESS` for a `MediaResult` with no error and `ExitStatus.REJECTED` for one with a `PublicError` — no new branching should be needed in `exit_status` for this to pass.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_models.py tests/config/test_models.py tests/core/test_errors.py tests/cli/test_outcome.py -v`
  Expected: FAIL because the media package, settings fields, and error/result contracts do not exist.

- [ ] **Step 3: Implement the contracts**

```python
class MediaSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    uploads: UploadSettings = Field(default_factory=lambda: UploadSettings())
    sanitize: SanitizeSettings = Field(default_factory=lambda: SanitizeSettings())
    publish: PublishSettings = Field(default_factory=lambda: PublishSettings())
    metadata: MetadataSettings = Field(default_factory=lambda: MetadataSettings())
    provenance: ProvenanceSettings = Field(default_factory=lambda: ProvenanceSettings())
    c2pa: C2PASettings = Field(default_factory=lambda: C2PASettings())
```

  Give each nested model the exact defaults from the spec's `[media.uploads]`/`[media.sanitize]`/`[media.publish]`/`[media.metadata]`/`[media.provenance]`/`[media.c2pa]` tables. Wire `media: MediaSettings = Field(default_factory=MediaSettings)` into `Settings`, next to `generation`. Add `ErrorCode.MEDIA_VERIFICATION_FAILED = "media_verification_failed"`. Define `MediaResult` as a single-outcome model:

```python
class MediaResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    operation: Literal["media.inspect", "media.sanitize", "media.publish"]
    source: Path
    source_bytes: int
    output_path: Path | None = None
    media_type: str | None = None
    width: int | None = None
    height: int | None = None
    output_bytes: int | None = None
    inspection: ImageInspection | None = None  # populated only for media.inspect
    transform: MediaTransformReport | None = None  # populated only for sanitize/publish
    warnings: tuple[str, ...] = Field(default=())
    error: PublicError | None = None

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        succeeded = self.error is None
        has_outcome = self.inspection is not None or self.output_path is not None
        if succeeded != has_outcome:
            raise ValueError("a media result requires one successful outcome or one error")
        return self
```

  Keep secrets out of every media model and result. Make `digital_source_type = "auto"` distinct from an explicit controlled-vocabulary URI. Extend `cli/outcome.py`'s `PublicResult` union and `cli/render.py` with `render_media_result` (JSON dump, plus a short human summary: operation, source, output path or error, dimensions, byte sizes).

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_models.py tests/config/test_models.py tests/core/test_errors.py tests/cli/test_outcome.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media src/pixgen/config/models.py src/pixgen/core/errors.py src/pixgen/cli/outcome.py src/pixgen/cli/render.py tests/media tests/config/test_models.py tests/core/test_errors.py tests/cli/test_outcome.py
  git commit -m "feat: add media policy and result contracts"
  ```

### Task 2: Build metadata inspection and safe image facts

**Files:**
- Create: `src/pixgen/media/inspect.py`
- Create: `src/pixgen/media/metadata.py`
- Modify: `src/pixgen/images/models.py` only if `LocalImage` needs a field this task's tests reveal it's missing
- Test: `tests/media/test_inspect.py`
- Test: `tests/images/test_inspect.py`
- Fixtures: `tests/fixtures/media/` with small generated images containing representative metadata

**Interfaces:**
- `inspect_image(image: LocalImage) -> ImageInspection` returns decoded format, dimensions, alpha, orientation, sRGB state, metadata categories, C2PA presence, and redacted AI signal summaries.
- `metadata.inspect_metadata(content: bytes, media_type: str) -> MetadataReport` returns categories and safe counts/names only, never raw values. Uses `pyexiv2` for EXIF/IPTC/XMP presence (it is the only library in the dependency set that parses IPTC IIM at all — Pillow cannot) and a plain byte-pattern search for a `c2pa`/`urn:c2pa:` marker in JPEG APP11/PNG `caBX`/RIFF chunks for C2PA presence detection, since full C2PA parsing is out of scope while signing/verification are deferred.
- `pixgen.images.inspect.load_image` continues to own decode-verification and stays limited to the three supported static formats; this task does not change its supported-format set.

- [ ] **Step 1: Add fixture-based failing tests**

  Cover clean PNG/JPEG/WebP, JPEG orientation, GPS/EXIF, XMP/IPTC markers, PNG ancillary chunks, WebP metadata chunks, a synthetic C2PA-marker fixture, invalid files, and redaction of GPS/prompt values.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_inspect.py tests/images/test_inspect.py -v`
  Expected: FAIL because inspection and metadata reporting do not exist.

- [ ] **Step 3: Add the dependency and implement safe inspection**

```toml
[project]
dependencies = [
    # ...existing entries unchanged...
    "pyexiv2>=2.16,<3",
]
```

  Run: `uv lock`

  Use Pillow for decoded image facts (format, dimensions, alpha, orientation via EXIF tag 274) and `pyexiv2` for EXIF/IPTC/XMP category presence and safe counts. Report unknown metadata-bearing containers as `unknown` rather than guessing. Never expose raw values — only category names, counts, and booleans. Keep low-level file loading (`pixgen.images.inspect.load_image`) separate from policy decisions (this module).

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_inspect.py tests/images/test_inspect.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add pyproject.toml uv.lock src/pixgen/media/inspect.py src/pixgen/media/metadata.py tests/media/test_inspect.py tests/images/test_inspect.py tests/fixtures/media
  git commit -m "feat: inspect image metadata safely"
  ```

### Task 3: Implement the verified private sanitization pipeline

**Files:**
- Create: `src/pixgen/media/sanitize.py`
- Create or reuse: `src/pixgen/images/transform.py` — see the ordering note below
- Test: `tests/media/test_sanitize.py`
- Test: `tests/images/test_transform.py` (only if this task creates `images/transform.py`)

**Interfaces:**
- `sanitize_image(image: LocalImage, policy: SanitizeSettings) -> SanitizedImage` returns sanitized bytes, MIME type, dimensions, and a `MediaTransformReport` without writing a final path.
- `sanitize.verify_private_output(content: bytes, media_type: str) -> ImageInspection` raises `PixgenError(ErrorCode.MEDIA_VERIFICATION_FAILED, ...)` when the output is not decodable, normalized, sRGB, or metadata-free.

**Ordering note (codec reuse):** the spec is explicit that "the media layer should not add a second image codec pipeline," and the image-optimization plan's `optimization/local.py` needs the identical decode-once → `ImageOps.exif_transpose` → re-encode-with-fresh-kwargs path. Check which plan lands first before writing this task's implementation:
- **If `docs/superpowers/plans/2026-09-19-image-optimization.md` Task 5 has already landed**, its private `_load_source`/encode helpers in `optimization/local.py` are not importable as-is (they're private to that module by design). Extract the shared pieces into `src/pixgen/images/transform.py` as public functions (`load_normalized(path: Path) -> Image.Image`, `encode_stripped(image: Image.Image, fmt: ImageFormat, *, quality: int | None, icc_profile: bytes | None) -> bytes`) in *that same PR*, have `optimization/local.py` switch to calling them, and have this task's `sanitize.py` call them too. This is a small refactor of already-landed code, not new design.
- **If this plan lands first**, create `src/pixgen/images/transform.py` directly with those same two public functions, and leave a note in this plan's PR description telling the optimization plan's implementer to import them instead of rewriting `_load_source`.
- Either way, do not let `media/sanitize.py` depend on `pixgen.optimization.*` or vice versa — the shared code belongs in `pixgen/images/`, which both features already depend on per `AGENTS.md`'s layering (`images/` "reads local inputs, returns bytes + metadata").

- [ ] **Step 1: Write failing sanitization tests**

  Assert correct orientation pixels, sRGB output, removal of EXIF/GPS/IPTC/XMP/comments/profiles/C2PA, source immutability, format preservation, transparency preservation, and rejection of nonconforming output.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_sanitize.py -v`
  Expected: FAIL because the pipeline does not exist.

- [ ] **Step 3: Implement decode, normalize, strip, encode, and verify**

  Decode once via the shared `images/transform.load_normalized`, convert to sRGB pixels, and encode using the selected format via `images/transform.encode_stripped` with an explicit metadata-free encoder configuration for PNG, JPEG, and WebP (construct save kwargs from scratch; never pass `xmp=` or `exif=` on a private output, even for WebP, since Pillow *would* otherwise write WebP XMP if given any). Reopen the encoded bytes and verify all private invariants before returning them.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_sanitize.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media/sanitize.py src/pixgen/images/transform.py tests/media/test_sanitize.py tests/images/test_transform.py
  git commit -m "feat: add verified private image sanitization"
  ```

### Task 4: Add public publishing metadata and provenance rules

**Files:**
- Create: `src/pixgen/media/provenance.py`
- Create: `src/pixgen/media/publish.py`
- Test: `tests/media/test_publish.py`
- Test: `tests/media/test_provenance.py`

**Interfaces:**
- `resolve_provenance(settings: ProvenanceSettings, *, trusted_system: str | None, trusted_version: str | None, trusted_source_type: str | None) -> ProvenanceValues` never infers authorship.
- `build_public_metadata(settings: MetadataSettings, provenance: ProvenanceValues) -> PublicMetadata` returns only non-null configured fields and trusted provenance.
- `publish_image(image: LocalImage, *, sanitize: SanitizeSettings, publish: PublishSettings, metadata: MetadataSettings, provenance: ProvenanceSettings, trusted_provenance: TrustedProvenance | None) -> PublishedImage` returns verified public bytes and a `MediaTransformReport`.
- `write_public_metadata(content: bytes, media_type: str, fields: PublicMetadata) -> bytes` is the one function that touches `pyexiv2`; everything else in this task stays format-agnostic.

- [ ] **Step 1: Write failing publishing and provenance tests**

  Pin XMP/IPTC-compatible mappings for credit line (IPTC Credit Line / XMP `photoshop:Credit`), copyright notice (IPTC Copyright Notice / XMP `dc:rights`), rights URL (IPTC Web Statement of Rights / XMP `xmpRights:WebStatement`), and Licensor URL (PLUS/IPTC Licensor URL sub-field); omission of null values; URL validation; prompt defaults; trusted AI system/version output using the IPTC Photo Metadata Standard 2025.1 field names; no invented AI source type; transparent-JPEG rejection; and absence of source metadata. Add a round-trip test: publish with only `credit_line` set, then re-open the output with `pyexiv2` and assert that field is present and every other IPTC/XMP field the *source* had is absent.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_publish.py tests/media/test_provenance.py -v`
  Expected: FAIL because public metadata and provenance mapping do not exist.

- [ ] **Step 3: Implement the minimal standards-based writer**

  Write only the selected XMP/IPTC-compatible properties via `pyexiv2` for JPEG/PNG, and via Pillow's native `xmp=` packet for WebP (building the XMP packet string once and reusing it for both paths, so there is one source of truth for the field mapping regardless of which writer touches the bytes). Do not preserve source metadata — `publish_image` always starts from the *sanitized* (metadata-free) bytes from Task 3, then adds only the allowlisted fields. Keep C2PA disabled and reject an enabled setting before encoding.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_publish.py tests/media/test_provenance.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media/provenance.py src/pixgen/media/publish.py tests/media/test_publish.py tests/media/test_provenance.py
  git commit -m "feat: publish standards-based image metadata"
  ```

### Task 5: Add media application orchestration and CLI commands

**Files:**
- Create: `src/pixgen/media/application.py`
- Create: `src/pixgen/cli/media.py`
- Modify: `src/pixgen/cli/app.py`
- Modify: `src/pixgen/runtime.py`
- Create: `tests/media/test_application.py`
- Create: `tests/cli/test_media.py`

**Interfaces:**
- `MediaApplication.inspect(path: Path) -> MediaResult`.
- `MediaApplication.sanitize(path: Path, *, output: Path | None, format: MediaFormat | None, force: bool, mkdir: bool) -> MediaResult`.
- `MediaApplication.publish(path: Path, *, output: Path | None, format: MediaFormat | None, quality: int | None, max_dimension: int | None, force: bool, mkdir: bool) -> MediaResult`.
- `build_media_app() -> cyclopts.App` exposes `inspect`, `sanitize`, and `publish` with `--json` and the exact option contracts in the spec, following the same `@app.default @cli_command()` pattern already used in `cli/image.py`.
- `runtime.Runtime` gains a `media_application: MediaApplication` field; `build_runtime()` constructs it from `settings.media`; `cli/app.py`'s `build_app` takes it as a new parameter and registers `app.command(build_media_app(media_application))`.

- [ ] **Step 1: Write failing application and CLI tests**

  Cover command parsing, one-input enforcement, default output planning (reuse `pixgen.artifacts.plan_output`'s single-output path the same way `create --output` does), `--format`, `--quality`, `--max-dimension`, `--force`, `--mkdir`, human output, JSON output, read-only `inspect` (no filesystem write), and `MediaResult`-shaped error envelopes for `PixgenError`/`ValidationError` via the existing `cli_command()` decorator.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_application.py tests/cli/test_media.py -v`
  Expected: FAIL because the application and command group do not exist.

- [ ] **Step 3: Implement orchestration and CLI registration**

  Load settings once through `runtime.build_runtime()`, reuse `pixgen.artifacts.plan_output`/`write_atomic` for output planning and promotion, stage bytes in a sibling temp file before promotion (matching the optimization plan's staging approach in spirit, but single-file, so no multi-variant aggregation is needed), and map `PixgenError` to `MediaResult(error=PublicError(...))` via `cli_command()`. Keep the CLI free of image decoding and metadata logic — that lives in `media/sanitize.py`/`media/publish.py`.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_application.py tests/cli/test_media.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media/application.py src/pixgen/cli/media.py src/pixgen/cli/app.py src/pixgen/runtime.py tests/media/test_application.py tests/cli/test_media.py
  git commit -m "feat: add media inspect sanitize and publish commands"
  ```

### Task 6: Integrate automatic sanitized provider uploads and token-aware preparation

**Files:**
- Create: `src/pixgen/media/provider.py`
- Modify: `src/pixgen/application.py`
- Modify: `src/pixgen/providers/base.py` only if prepared media needs a policy report
- Modify: `src/pixgen/providers/openai.py` only if provider-specific request constraints need an explicit adapter hook
- Modify: `src/pixgen/providers/gemini.py` only if provider-specific request constraints need an explicit adapter hook
- Test: `tests/media/test_provider.py`
- Modify: `tests/application/test_application.py`
- Modify: `tests/providers/test_openai.py` and `tests/providers/test_gemini.py` only for byte/format assertions

**Interfaces:**
- `prepare_provider_media(images: tuple[LocalImage, ...], *, model: ModelSpec, settings: MediaSettings) -> tuple[LocalImage, ...]` returns sanitized and, only when needed, downsized upload images.
- `provider_upload_report(...) -> ProviderPreparationReport` records source/upload dimensions, formats, and whether preparation changed the image.
- `ImageApplication` gains a way to reach `prepare_provider_media`: add an optional constructor parameter (e.g. `media_settings: MediaSettings | None = None`, defaulting to `None` meaning "sanitization disabled" for callers that don't pass it, though `runtime.build_runtime()` always will) rather than a new class dependency injected separately — `ImageApplication` already reads everything else off `self._settings`, so reading `self._settings.media` there is the natural fit and needs no new constructor plumbing.

- [ ] **Step 1: Write failing integration tests**

  Assert original bytes are never passed to OpenAI or Gemini when `settings.media.uploads.sanitize` is enabled; sanitization occurs once per source; suitable images avoid a second encode; oversized images are bounded near the initial 2048-pixel policy; transparency is preserved; multiple references retain order; temporary files are removed by default; and reports contain no sensitive metadata.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_provider.py tests/application/test_application.py tests/providers/test_openai.py tests/providers/test_gemini.py -v`
  Expected: FAIL because provider preparation is not integrated.

- [ ] **Step 3: Implement provider-aware preparation**

  In `ImageApplication._prepare` (`src/pixgen/application.py`), call `prepare_provider_media` on the loaded images before constructing `PreparedMedia`, only when `self._settings.media.uploads.sanitize` is true. Use model/provider capability data (`ModelSpec.media[role]`, already used by `_validate_media`) for format and byte limits, and a conservative dimension bound for oversized inputs. Preserve PNG for alpha/masks and use JPEG or WebP only for opaque photographic reductions. `PreparedMedia` already carries a `LocalImage` — prepared images are just a different `LocalImage` value, so no change to `providers/base.py`'s `PreparedMedia`/`ImageProvider` contract should be needed; only touch `providers/openai.py`/`providers/gemini.py` if a concrete provider-specific limit (not just the general 2048px bound) turns out to be necessary during implementation.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_provider.py tests/application/test_application.py tests/providers/test_openai.py tests/providers/test_gemini.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media/provider.py src/pixgen/application.py src/pixgen/providers/base.py src/pixgen/providers/openai.py src/pixgen/providers/gemini.py tests/media/test_provider.py tests/application/test_application.py tests/providers/test_openai.py tests/providers/test_gemini.py
  git commit -m "feat: sanitize and optimize provider image uploads"
  ```

### Task 7: Document the commands and run the complete verification suite

**Files:**
- Modify: `README.md`
- Modify: `pixgen.toml`
- Create: `tests/media/test_end_to_end.py` if an isolated fixture-level flow test is needed

- [ ] **Step 1: Add documentation and example defaults**

  Document ingress sanitization, private versus public output, metadata fields, AI provenance limits, provider resizing/token behaviour, C2PA deferral, the `pyexiv2` dependency's role, and one-file command examples. Add the approved media defaults to `pixgen.toml` as a `[media.*]` block (matching how `[generation]` already appears there) without credentials or personal metadata.

- [ ] **Step 2: Run the complete checks**

  Run: `just lint && just type-check && just test`
  Expected: all commands exit successfully.

- [ ] **Step 3: Run the full hook suite**

  Run: `just check`
  Expected: all hooks pass.

- [ ] **Step 4: Review the final diff and verify repository state**

  Run: `git diff --check` and `git status --short`.
  Expected: no whitespace errors; only intentional media feature changes remain.

- [ ] **Step 5: Commit**

  ```bash
  git add README.md pixgen.toml tests/media/test_end_to_end.py
  git commit -m "docs: document media privacy workflows"
  ```

## Self-review checklist

- Spec coverage: Tasks 1-2 cover configuration and inspection; Task 3 covers private sanitization; Task 4 covers publishing and IPTC provenance; Task 5 covers commands and atomic outputs; Task 6 covers ingress preparation and provider token optimization; Task 7 covers documentation and the required verification commands.
- Interface consistency: `LocalImage` remains the input boundary; `SanitizedImage` and `PublishedImage` carry bytes and reports; `MediaResult` is the one public result type, added to `cli/outcome.py`'s `PublicResult` union without a new `exit_status` branch; provider preparation returns `LocalImage` values consumed by the existing `PreparedMedia` contract.
- Dependency honesty: `pyexiv2` is a real, added dependency (Task 2) — the plan no longer claims Pillow or a nonexistent `filetype` package can write XMP/IPTC.
- Codec reuse: Task 3 explicitly resolves the "second codec pipeline" conflict with the image-optimization plan by sharing `pixgen/images/transform.py`, with an explicit ordering note for whichever plan lands second.
- Scope: no task adds audio/video, batch processing, C2PA signing, or public provider tuning flags.
- Review focus: each of the six high-risk input classes has a named test owner above.
- Verification: no task claims completion without its focused tests; the final task runs `just lint && just type-check && just test` and `just check`.
