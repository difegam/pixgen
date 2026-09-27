# Media sanitization and publishing commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add image-only `media inspect`, `media sanitize`, and `media publish` commands, plus automatic private/provider preparation for image uploads.

**Architecture:** Build one local image pipeline for inspection, pixel normalization, metadata removal, standards-based public metadata writing, verification, and atomic promotion. Keep CLI parsing and rendering at the edge, keep policy/result models in `media`, and invoke ingress preparation from `ImageApplication` before provider requests. Reuse `artifacts` for final promotion and the planned local optimization engine for codec operations.

**Tech Stack:** Python 3.14, Pydantic frozen models, Pillow for local decode/transform/encode, existing `filetype`, Cyclopts, Rich, pytest, Pyrefly, Ruff, and Pixgen's atomic artifact writer.

**Spec:** `docs/superpowers/specs/2026-09-27-media-commands-design.md`

## Global Constraints

- Support one static PNG, JPEG, or WebP image per media command in v1.
- Never modify the source file.
- Never upload the source file when `media.uploads.sanitize = true`.
- Private outputs always normalize orientation and sRGB, remove source metadata and C2PA, and re-encode.
- Public outputs write only configured rights/provenance metadata.
- Do not infer AI authorship from pixels, filenames, or weak metadata.
- Prompt and prompt-writer metadata are disabled by default.
- `media.c2pa.enabled = true` fails until signing and verification are implemented.
- Provider preparation downsizes only when needed and does not expose provider-specific tuning flags in v1.
- Use `uv run pytest`, `uv run pyrefly check`, and `just lint`; the type checker is Pyrefly, not mypy.
- Use British English in docstrings, Google-style docstrings, frozen Pydantic models, and `from __future__ import annotations` in production Python modules.
- Do not make real network requests or use real credentials in tests.

## Review Focus

- JPEG EXIF orientation with GPS metadata: pixels must rotate correctly while all source metadata disappears. Test in Task 3.
- PNG ancillary chunks and WebP XMP/EXIF: private outputs must not retain metadata through a format-specific side channel. Test in Task 3.
- Transparent image published as JPEG: reject before writing or changing the source. Test in Task 4.
- An arbitrary local image with AI-looking text or weak metadata: do not invent an AI provenance claim. Test in Task 4.
- Oversized provider input with multiple references: sanitize once per source, downscale only the oversized prepared copy, and upload no original bytes. Test in Task 6.

### Task 1: Add media policy models, configuration, and error/result contracts

**Files:**
- Create: `src/pixgen/media/__init__.py`
- Create: `src/pixgen/media/models.py`
- Create: `src/pixgen/media/results.py`
- Modify: `src/pixgen/config/models.py`
- Modify: `src/pixgen/core/errors.py`
- Test: `tests/media/test_models.py`
- Test: `tests/config/test_models.py`
- Test: `tests/core/test_errors.py`

**Interfaces:**
- Produces frozen policy models `UploadSettings`, `SanitizeSettings`, `PublishSettings`, `MetadataSettings`, `ProvenanceSettings`, and `C2PASettings` under a frozen `MediaSettings` model.
- Produces `MediaFormat`, `MetadataCategory`, `DigitalSourceType`, `ImageInspection`, `MediaOperationResult`, and `MediaTransformReport` models.
- Produces `MediaErrorCode` values for unsupported media, transformation failure, and verification failure while preserving existing `ErrorCode` behavior.
- `Settings.media` exposes `MediaSettings` with the exact defaults from the spec.

- [ ] **Step 1: Write failing model and configuration tests**

  Pin defaults, frozen/extra-forbid behavior, valid quality and dimension ranges, `format = null`, URL validation, enum values, and rejection of `c2pa.enabled = true` until signing support exists.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_models.py tests/config/test_models.py tests/core/test_errors.py -v`
  Expected: FAIL because the media package, settings fields, and error/result contracts do not exist.

- [ ] **Step 3: Implement the contracts**

  Add the models with frozen Pydantic configuration and wire `MediaSettings` into `Settings`. Keep secrets out of every media model and result. Make `digital_source_type = "auto"` distinct from an explicit controlled-vocabulary URI.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_models.py tests/config/test_models.py tests/core/test_errors.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media src/pixgen/config/models.py src/pixgen/core/errors.py tests/media tests/config/test_models.py tests/core/test_errors.py
  git commit -m "feat: add media policy contracts"
  ```

### Task 2: Build metadata inspection and safe image facts

**Files:**
- Create: `src/pixgen/media/inspect.py`
- Create: `src/pixgen/media/metadata.py`
- Modify: `src/pixgen/images/models.py`
- Modify: `src/pixgen/images/inspect.py`
- Test: `tests/media/test_inspect.py`
- Test: `tests/images/test_inspect.py`
- Fixtures: `tests/fixtures/media/` with small generated images containing representative metadata

**Interfaces:**
- `inspect_image(image: LocalImage) -> ImageInspection` returns decoded format, dimensions, alpha, orientation, sRGB state, metadata categories, C2PA presence, and redacted AI signal summaries.
- `metadata.inspect_metadata(content: bytes, media_type: str) -> MetadataReport` returns categories and safe counts/names only, never raw values.
- `images.load_image()` continues to return validated `LocalImage` values and remains limited to supported static formats.

- [ ] **Step 1: Add fixture-based failing tests**

  Cover clean PNG/JPEG/WebP, JPEG orientation, GPS/EXIF, XMP/IPTC markers, PNG ancillary chunks, WebP metadata chunks, C2PA presence detection, invalid files, and redaction of GPS/prompt values.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_inspect.py tests/images/test_inspect.py -v`
  Expected: FAIL because inspection and metadata reporting do not exist.

- [ ] **Step 3: Implement safe inspection**

  Use Pillow for decoded image facts and format-specific metadata parsing. Detect known metadata containers conservatively, report unknown metadata-bearing containers as `unknown`, and never expose payload contents. Keep low-level file loading separate from policy decisions.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_inspect.py tests/images/test_inspect.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media/inspect.py src/pixgen/media/metadata.py src/pixgen/images/models.py src/pixgen/images/inspect.py tests/media/test_inspect.py tests/images/test_inspect.py tests/fixtures/media
  git commit -m "feat: inspect image metadata safely"
  ```

### Task 3: Implement the verified private sanitization pipeline

**Files:**
- Create: `src/pixgen/media/sanitize.py`
- Create: `src/pixgen/media/transform.py`
- Modify: `src/pixgen/artifacts.py` only if a shared staged-bytes helper is required
- Test: `tests/media/test_sanitize.py`
- Test: `tests/media/test_transform.py`

**Interfaces:**
- `sanitize_image(image: LocalImage, policy: SanitizeSettings) -> SanitizedImage` returns sanitized bytes, MIME type, dimensions, and a `MediaTransformReport` without writing a final path.
- `transform.normalize_pixels(image: LocalImage, *, normalize_orientation: bool, normalize_srgb: bool) -> NormalizedImage` applies orientation and sRGB conversion.
- `sanitize.verify_private_output(content: bytes, media_type: str) -> ImageInspection` raises `PixgenError` with the media verification code when the output is not decodable, normalized, sRGB, or metadata-free.

- [ ] **Step 1: Write failing sanitization tests**

  Assert correct orientation pixels, sRGB output, removal of EXIF/GPS/IPTC/XMP/comments/profiles/C2PA, source immutability, format preservation, transparency preservation, and rejection of nonconforming output.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_sanitize.py tests/media/test_transform.py -v`
  Expected: FAIL because the pipeline does not exist.

- [ ] **Step 3: Implement decode, normalize, strip, encode, and verify**

  Use Pillow to decode once, apply EXIF orientation before dropping the tag, convert to sRGB pixels, and encode using the selected format. Use an explicit metadata-free encoder configuration for PNG, JPEG, and WebP. Reopen the encoded bytes and verify all private invariants before returning them.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `uv run pytest tests/media/test_sanitize.py tests/media/test_transform.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/pixgen/media/sanitize.py src/pixgen/media/transform.py src/pixgen/artifacts.py tests/media/test_sanitize.py tests/media/test_transform.py
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
- `publish_image(image: LocalImage, *, sanitize: SanitizeSettings, publish: PublishSettings, metadata: MetadataSettings, provenance: ProvenanceSettings, trusted_provenance: TrustedProvenance | None) -> PublishedImage` returns verified public bytes and a transform report.

- [ ] **Step 1: Write failing publishing and provenance tests**

  Pin XMP/IPTC-compatible mappings for credit line, copyright notice, rights URL, and Licensor URL; omission of null values; URL validation; prompt defaults; trusted AI system/version output; no invented AI source type; transparent-JPEG rejection; and absence of source metadata.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_publish.py tests/media/test_provenance.py -v`
  Expected: FAIL because public metadata and provenance mapping do not exist.

- [ ] **Step 3: Implement the minimal standards-based writer**

  Write only the selected XMP/IPTC-compatible properties. Use the IPTC 2025.1 names for AI system, AI system version, prompt, and prompt writer. Do not preserve source metadata. Keep C2PA disabled and reject an enabled setting before encoding.

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
- `MediaApplication.inspect(path: Path) -> MediaRunOutcome`.
- `MediaApplication.sanitize(path: Path, *, output: Path | None, format: MediaFormat | None, force: bool, mkdir: bool) -> MediaRunOutcome`.
- `MediaApplication.publish(path: Path, *, output: Path | None, format: MediaFormat | None, quality: int | None, max_dimension: int | None, force: bool, mkdir: bool) -> MediaRunOutcome`.
- `build_media_app(application: MediaApplication) -> cyclopts.App` exposes `inspect`, `sanitize`, and `publish` with `--json` and the exact option contracts in the spec.
- `build_app()` registers the media app and `build_runtime()` constructs the application with loaded settings.

- [ ] **Step 1: Write failing application and CLI tests**

  Cover command parsing, one-input enforcement, default output planning, `--format`, `--quality`, `--max-dimension`, `--force`, `--mkdir`, human output, JSON output, read-only inspect, and command-level error envelopes.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_application.py tests/cli/test_media.py -v`
  Expected: FAIL because the application and command group do not exist.

- [ ] **Step 3: Implement orchestration and CLI registration**

  Load settings once through the runtime, reuse `plan_output`/`save_artifact` semantics, stage bytes before promotion, and map `PixgenError` to the existing public result/error conventions. Keep the CLI free of image decoding and metadata logic.

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
- `ImageApplication._prepare()` performs preparation separately for each selected model so provider/model rules do not leak across requests.

- [ ] **Step 1: Write failing integration tests**

  Assert original bytes are never passed to OpenAI or Gemini when sanitization is enabled; sanitization occurs once per source; suitable images avoid a second encode; oversized images are bounded near the initial 2048-pixel policy; transparency is preserved; multiple references retain order; temporary files are removed by default; and reports contain no sensitive metadata.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/media/test_provider.py tests/application/test_application.py tests/providers/test_openai.py tests/providers/test_gemini.py -v`
  Expected: FAIL because provider preparation is not integrated.

- [ ] **Step 3: Implement provider-aware preparation**

  Apply the private sanitizer before provider validation. Use model/provider capability data for format and byte limits, and a conservative dimension bound for oversized inputs. Preserve PNG for alpha/masks and use JPEG or WebP only for opaque photographic reductions. Pass prepared bytes through the existing `PreparedMedia` contract.

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

  Document ingress sanitization, private versus public output, metadata fields, AI provenance limits, provider resizing/token behavior, C2PA deferral, and one-file command examples. Add the approved media defaults to `pixgen.toml` without credentials or personal metadata.

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
- Interface consistency: `LocalImage` remains the input boundary; `SanitizedImage` and `PublishedImage` carry bytes and reports; provider preparation returns `LocalImage` values consumed by the existing `PreparedMedia` contract.
- Scope: no task adds audio/video, batch processing, C2PA signing, or public provider tuning flags.
- Review focus: each of the five high-risk input classes has a named test owner above.
- Verification: no task claims completion without its focused tests; the final task runs `just lint && just type-check && just test` and `just check`.

