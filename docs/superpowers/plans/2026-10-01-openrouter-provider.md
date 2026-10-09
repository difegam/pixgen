# OpenRouter Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add OpenRouter image creation and the documented edit capabilities for three curated image models.

**Architecture:** Add a dedicated provider over OpenRouter's buffered Images API and keep its model catalogue and error mapping in the provider adapter. Preserve exact upstream model slugs beneath Pixgen's `openrouter` provider prefix, share only HTTP client construction and validated image decoding with OpenAI, and wire the provider through the existing lazy runtime, registry, and native CLI patterns.

**Tech Stack:** Python 3.14, Pydantic, `httpx2`, Cyclopts, pytest, Ruff, Pyrefly.

**Spec:** `docs/superpowers/specs/2026-10-01-openrouter-provider-design.md`

## Global Constraints

- Use `POST /api/v1/images` and the OpenRouter direct Images API.
- Use model IDs `openrouter/<author>/<slug>` and preserve the exact upstream `<author>/<slug>` in requests.
- Read provider keys from environment variables only; support `OPENROUTER_API_KEY` and `PIXGEN_OPENROUTER_API_KEY`.
- Do not add an OpenRouter SDK or another runtime dependency.
- Keep Pixgen variants as separate requests; do not send the OpenRouter `n` parameter.
- Keep Muse Image create-only until the Images API documents `input_references` support.
- Keep configured default create and edit models unchanged.

## Review Focus

- A nested model ID with an empty path segment must fail validation; cover it in Task 1's `test_rejects_invalid_nested_model_ids`.
- References must preserve order, media type, and bytes in the base64 data URLs; cover it in Task 3's `test_generate_includes_references_as_ordered_data_urls`.
- A missing response media type must use `image/png`; cover it in Task 3's `test_generate_defaults_missing_media_type_to_png`.
- Invalid response data and upstream error bodies must not leak base64 or raw provider text; cover them in Tasks 2 and 3's safe-error assertions.
- A missing key must not prevent catalogue commands from building or eagerly construct clients; cover it in Task 4's runtime tests.

---

### Task 1: Preserve nested upstream model slugs

**Files:**
- Modify: `src/pixgen/core/models.py`
- Test: `tests/core/test_models.py`

**Interfaces:**
- Produces: `ModelId` accepts one provider segment followed by one or more non-empty model path segments. `ModelSpec.provider` remains the first segment and `ModelSpec.model` remains the full remainder.

- [x] **Step 1: Add nested ID validation tests**

  Add `test_accepts_nested_provider_model_id` with
  `openrouter/google/gemini-3.1-flash-image`; assert `ModelId` preserves the
  input. Add `test_model_spec_splits_nested_provider_model_id` and assert the
  provider is `openrouter` while the model is
  `google/gemini-3.1-flash-image`. Extend invalid cases with empty
  intermediate and trailing segments, such as `openrouter//gemini-image` and
  `openrouter/google/`.

- [x] **Step 2: Run the focused tests and confirm the new case fails**

  Run: `uv run pytest tests/core/test_models.py -k 'nested or invalid' -v`

  Expected: the valid nested ID is rejected by the current one-slash pattern;
  existing invalid-ID assertions remain green.

- [x] **Step 3: Update the `ModelId` pattern**

  In `src/pixgen/core/models.py`, allow a provider segment and slash-separated
  model segments, each beginning with a lowercase alphanumeric character and
  followed only by lowercase alphanumerics, dots, underscores, or hyphens.
  Keep the existing overall minimum and maximum lengths.

- [x] **Step 4: Run the focused tests**

  Run: `uv run pytest tests/core/test_models.py -k 'nested or invalid' -v`

  Expected: PASS, including the new nested ID and malformed path assertions.

- [x] **Step 5: Commit the model ID contract**

  ```bash
  git add src/pixgen/core/models.py tests/core/test_models.py
  git commit -m "feat: allow nested provider model slugs"
  ```

### Task 2: Share HTTP construction and image decoding

**Files:**
- Create: `src/pixgen/providers/http.py`
- Modify: `src/pixgen/runtime.py`
- Modify: `src/pixgen/providers/openai.py`
- Test: `tests/providers/test_http.py`
- Test: `tests/providers/test_openai.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Produces: `make_http_client_factory(api_key: SecretStr | None, *, base_url: str, request_timeout_seconds: int) -> Callable[[], httpx2.AsyncClient] | None`.
- Produces: `decode_base64_image(encoded: str, *, media_type: str, provider_name: str) -> ProviderImage`.
- Consumes: the helper signatures above in OpenAI and later OpenRouter runtime composition.

- [x] **Step 1: Add failing tests for the shared HTTP helpers**

  Create `tests/providers/test_http.py` with:

  - `test_make_http_client_factory_returns_none_without_key`.
  - `test_make_http_client_factory_creates_authenticated_client_lazily`,
    asserting no client is constructed before the returned factory is called,
    then asserting base URL, bearer header, and timeout.
  - `test_decode_base64_image_returns_bytes_and_media_type`.
  - `test_decode_base64_image_rejects_invalid_or_empty_data_safely`, asserting
    `ErrorCode.PROVIDER_FAILURE` and no encoded data in the error message.

- [x] **Step 2: Run the helper tests and verify they fail**

  Run: `uv run pytest tests/providers/test_http.py -v`

  Expected: FAIL because `pixgen.providers.http` and the helpers do not exist.

- [x] **Step 3: Implement the two focused helpers**

  In `src/pixgen/providers/http.py`, implement the exact signatures above. Use
  `httpx2.AsyncClient`, `httpx2.Timeout(request_timeout_seconds)`, and a bearer
  Authorization header. Decode base64 with validation and reject empty bytes.

- [x] **Step 4: Run the helper tests**

  Run: `uv run pytest tests/providers/test_http.py -v`

  Expected: PASS.

- [x] **Step 5: Refactor OpenAI to use the helpers**

  Replace `get_open_ai_factory`'s client-building body in `runtime.py` with
  `make_http_client_factory(..., base_url="https://api.openai.com/v1", ...)`.
  Keep the public runtime composition behavior and laziness unchanged. Update
  OpenAI response decoding to validate its response envelope locally and then
  call `decode_base64_image` with its output format.

- [x] **Step 6: Run OpenAI and runtime tests**

  Run: `uv run pytest tests/providers/test_openai.py tests/test_runtime.py -v`

  Expected: PASS with OpenAI behavior unchanged and no eager client creation.

- [x] **Step 7: Commit the shared HTTP helpers**

  ```bash
  git add src/pixgen/providers/http.py src/pixgen/runtime.py src/pixgen/providers/openai.py tests/providers/test_http.py tests/providers/test_openai.py tests/test_runtime.py
  git commit -m "refactor: share provider HTTP helpers"
  ```

### Task 3: Add the OpenRouter catalogue and provider adapter

**Files:**
- Create: `src/pixgen/providers/openrouter.py`
- Create: `tests/providers/test_openrouter.py`
- Modify: `tests/providers/test_registry.py`

**Interfaces:**
- Produces: `OPENROUTER_CATALOGUE`, `OpenRouterGeminiParams`, `OpenRouterGPTImageParams`, and `OpenRouterProvider(client: httpx2.AsyncClient | None, client_factory: Callable[[], httpx2.AsyncClient] | None = None)`.
- Consumes: `make_http_client_factory` and `decode_base64_image` from Task 2.
- `OpenRouterProvider.name` is `"openrouter"`; its `catalogue` contains exactly the three spec IDs in the design spec.

- [x] **Step 1: Add failing catalogue and parameter tests**

  In `tests/providers/test_openrouter.py`, assert exact IDs and upstream model
  suffixes; create/edit operations and reference maxima (Gemini 14, GPT 16,
  Muse create-only); Gemini resolution and aspect-ratio validation; GPT quality,
  background, aspect-ratio, and compression validation; and absence of `n` and
  Muse provider-native parameters. Add a registry test proving nested
  `openrouter/google/...` IDs resolve to `OpenRouterProvider`.

- [x] **Step 2: Run the catalogue tests and verify they fail**

  Run: `uv run pytest tests/providers/test_openrouter.py tests/providers/test_registry.py -k 'openrouter or nested' -v`

  Expected: FAIL because the OpenRouter adapter and catalogue do not exist.

- [x] **Step 3: Implement model parameter types and catalogue**

  Define model-owned parameter types in `openrouter.py`. Match the spec's
  parameter values and aspect-ratio lists exactly. Give Muse only the
  `IMAGE_CREATE` operation and no `input_references` capability. Use
  `ModelDefinition` aspect-ratio overrides that pass through
  `{"aspect_ratio": ratio}` for ratios the model supports.

- [x] **Step 4: Run catalogue tests**

  Run: `uv run pytest tests/providers/test_openrouter.py tests/providers/test_registry.py -k 'openrouter or nested' -v`

  Expected: PASS for catalogue, parameters, registry ownership, and operation
  validation.

- [x] **Step 5: Add failing generation and response tests**

  Add tests asserting that create posts to `/api/v1/images` with the exact
  upstream model slug and only set parameters; edit sends references as
  ordered `input_references` data URLs retaining source media types and bytes;
  a response with `media_type` returns that type; an omitted type defaults to
  `image/png`; missing credentials raise `CREDENTIAL_UNAVAILABLE`; and invalid
  or empty response data raises a safe provider error.

- [x] **Step 6: Run generation tests and verify they fail**

  Run: `uv run pytest tests/providers/test_openrouter.py -k 'generate or response' -v`

  Expected: FAIL because generation has not yet been implemented.

- [x] **Step 7: Implement lazy client access and generation**

  Build the JSON payload from the validated request, base64 data URLs from
  `PreparedImageRequest.media`, and response models for the OpenRouter
  `data[].b64_json` and optional `data[].media_type` fields. Call the shared
  decoder for the first result. Use the client timeout supplied by runtime
  configuration; do not hardcode the project timeout in the adapter. Wrap
  request failures through `_map_error`, initially returning a safe
  `PROVIDER_FAILURE` for unclassified exceptions.

- [x] **Step 8: Add failing provider error mapping tests**

  Parameterise mocked HTTP responses and transport exceptions to assert:
  timeout → `TIMEOUT`, connect/5xx → `PROVIDER_UNAVAILABLE`, 401/403 →
  `AUTHENTICATION_FAILED`, 404 → `MODEL_NOT_FOUND`, 429 → `RATE_LIMITED`,
  ordinary 4xx → `INVALID_REQUEST`, and recognised moderation/content policy
  4xx → `CONTENT_REJECTED`. Assert raw response bodies are not exposed.

- [x] **Step 9: Implement OpenRouter error mapping and rerun adapter tests**

  Keep the status mapping local to `OpenRouterProvider._map_error`; run:

  `uv run pytest tests/providers/test_openrouter.py tests/providers/test_http.py tests/providers/test_registry.py -v`

  Expected: PASS.

- [x] **Step 10: Commit the provider adapter**

  ```bash
  git add src/pixgen/providers/openrouter.py tests/providers/test_openrouter.py tests/providers/test_registry.py
  git commit -m "feat: add OpenRouter image provider"
  ```

### Task 4: Wire credentials, runtime, and provider-native CLI

**Files:**
- Create: `src/pixgen/providers/openrouter_cli.py`
- Modify: `src/pixgen/config/models.py`
- Modify: `src/pixgen/runtime.py`
- Modify: `src/pixgen/providers/shared.py`
- Test: `tests/config/test_models.py`
- Test: `tests/test_runtime.py`
- Test: `tests/cli/test_provider_commands.py`

**Interfaces:**
- Produces: `Settings.openrouter_api_key: SecretStr | None`, loaded from `OPENROUTER_API_KEY` or `PIXGEN_OPENROUTER_API_KEY`.
- Produces: `OpenRouterCliFactory`, with `name = "openrouter"` and create/edit commands using OpenRouter's model parameter types.
- Modifies: `normalize_model_id(value: str, *, prefix: str, error_message: str, allow_nested: bool = False) -> str`; keep current default behavior and enable nested provider-local slugs only for OpenRouter.

- [x] **Step 1: Add failing credential and runtime tests**

  Test both environment aliases on `Settings`. Extend runtime tests to assert
  the provider and CLI factory are registered, the configured key makes
  OpenRouter available without constructing a client, and a missing key leaves
  model-list construction usable with the provider unavailable.

- [x] **Step 2: Run the focused tests and verify they fail**

  Run: `uv run pytest tests/config/test_models.py tests/test_runtime.py -k 'openrouter' -v`

  Expected: FAIL because the settings field, provider, and factory are absent.

- [x] **Step 3: Add the OpenRouter settings field and runtime wiring**

  Add `openrouter_api_key` using `AliasChoices("PIXGEN_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")`. Build its lazy client factory with the Task 2 helper and base URL `https://openrouter.ai/api/v1`; register `OpenRouterProvider` and `OpenRouterCliFactory` alongside the current providers.

- [x] **Step 4: Run the credential and runtime tests**

  Run: `uv run pytest tests/config/test_models.py tests/test_runtime.py -k 'openrouter' -v`

  Expected: PASS; no client is created while constructing the runtime.

- [x] **Step 5: Add failing nested native CLI normalization tests**

  Add provider-command tests showing these model arguments normalise exactly
  as follows:

  ```text
  google/gemini-3.1-flash-image  -> openrouter/google/gemini-3.1-flash-image
  openrouter/meta/muse-image     -> openrouter/meta/muse-image
  openai/gpt-image-2.5-sunburst  -> openrouter/openai/gpt-image-2.5-sunburst
  ```

  Confirm current OpenAI and Gemini commands still reject nested local model
  names.

- [x] **Step 6: Run the CLI tests and verify the OpenRouter cases fail**

  Run: `uv run pytest tests/cli/test_provider_commands.py -k 'openrouter or nested' -v`

  Expected: FAIL because OpenRouter CLI and nested normalization are absent.

- [x] **Step 7: Implement the provider CLI and scoped nested normalization**

  Add create/edit commands following the OpenAI/Gemini factories. Update
  `normalize_model_id` with `allow_nested=False`; when enabled, validate the
  prefixed value against `ModelId`, unless the value already has the target
  provider prefix. Set it to true only in OpenRouter's model normalizer. Keep
  command-level prompt, parameter, output, variant, and timeout options
  consistent with existing providers.

- [x] **Step 8: Run CLI, runtime, and provider integration tests**

  Run: `uv run pytest tests/cli/test_provider_commands.py tests/cli/test_app.py tests/test_runtime.py tests/providers/test_openrouter.py -v`

  Expected: PASS; Muse edit is rejected during registry validation before
  `CommandInvoker.invoke` reaches generation.

- [x] **Step 9: Commit runtime and CLI wiring**

  ```bash
  git add src/pixgen/config/models.py src/pixgen/runtime.py src/pixgen/providers/shared.py src/pixgen/providers/openrouter_cli.py tests/config/test_models.py tests/test_runtime.py tests/cli/test_provider_commands.py
  git commit -m "feat: wire OpenRouter credentials and CLI"
  ```

### Task 5: Document OpenRouter and run project checks

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docs/superpowers/specs/2026-10-01-openrouter-provider-design.md`
- Add: `docs/superpowers/plans/2026-10-01-openrouter-provider.md`

**Interfaces:**
- Documents environment key aliases, nested model IDs, supported model operations, and provider-native commands. Does not change `pixgen.toml` defaults.

- [x] **Step 1: Update user documentation**

  Add `OPENROUTER_API_KEY` and `PIXGEN_OPENROUTER_API_KEY` to the credential
  section, add the OpenRouter key to `.env.example`, document the three exact
  model IDs and their create/edit capabilities, and show one create and one
  supported edit example. State that Muse edit is not currently available via
  the Images API. Leave default model configuration unchanged.

- [x] **Step 2: Review documentation and patch formatting**

  Run: `git diff --check`

  Expected: no whitespace errors and examples use the exact IDs registered in
  the catalogue.

- [x] **Step 3: Run repository lint, type, and test checks**

  Run these commands in order:

  ```bash
  just lint
  just type-check
  just test
  ```

  `just lint` and `just type-check` pass. `just test` reports 350 passed and
  five failures in existing CLI rendering/parsing tests. All five failures
  reproduce on base commit `3ab37b6`; they do not touch OpenRouter code.

- [x] **Step 4: Commit the documentation**

  ```bash
  git add README.md .env.example docs/superpowers/specs/2026-10-01-openrouter-provider-design.md docs/superpowers/plans/2026-10-01-openrouter-provider.md
  git commit -m "docs: add OpenRouter usage"
  ```
