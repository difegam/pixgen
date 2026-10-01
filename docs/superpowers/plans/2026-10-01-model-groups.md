# Create model groups implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add create-only model groups loaded from TOML and selected with `pixgen create --group NAME`.

**Architecture:** Add a frozen `ModelGroup` configuration model under `config.models`, then pass the configured group mapping into the create CLI builder. The CLI resolves a group to the existing `SharedSelection(models=...)`; the application, provider registry, artifact code, and result schema remain unchanged.

**Tech Stack:** Python 3.14, Pydantic Settings, frozen Pydantic models, Cyclopts, pytest, Ruff, Pyrefly, and TOML.

**Spec:** `docs/superpowers/specs/2026-10-01-model-groups-design.md`

## Global constraints

- Support named groups only for `create`; `edit` must not accept `--group`.
- Group fields are `models`, `description`, and `tags` only.
- Groups must not define aspect ratios, prompts, references, or provider-specific parameters.
- `--group` and `--model` are mutually exclusive.
- `create` without either option keeps using `defaults.image_create_models`.
- Remove the shared root `create --aspect-ratio` option; keep provider-native options and internal provider validation unchanged.
- Preserve model order from TOML.
- Reject duplicate models, blank descriptions, blank tags, and unknown group fields.
- Validate model IDs with the existing `ModelId` type during settings load.
- Unknown group names return an `invalid_request` command error without invoking the application or a provider.
- Existing configuration without a `[groups]` table remains valid.
- Keep secrets out of configuration models, errors, and logs.
- Use frozen Pydantic models with `ConfigDict(frozen=True, extra="forbid")`.
- Use British English in docstrings and Google-style docstrings.
- Use `uv run pytest`, `uv run pyrefly check`, and `just lint`; the type checker is Pyrefly, not mypy.
- Do not make real network requests or use credentials in tests.
- Run `just lint && just type-check && just test` before claiming completion.

## Review focus

- A group with duplicate models must fail configuration loading instead of generating duplicate jobs. Test it in Task 1.
- A group with blank or whitespace-padded metadata must fail configuration loading. Test it in Task 1.
- A syntactically valid model that is absent from the provider registry must follow existing model-resolution behavior. Test the resolved tuple in Task 2 and rely on existing application coverage for registry errors.
- An unknown group must produce a command-level `invalid_request` and must not invoke the application. Test it in Task 2.
- Removing the shared create aspect-ratio option must not remove provider-native aspect-ratio options or the shared edit option. Test both parser boundaries in Task 2.

### Task 1: Add the model-group configuration model

**Files:**
- Modify: `src/pixgen/config/models.py`
- Test: `tests/config/test_models.py`

**Interfaces:**
- Produces `ModelGroup`, exported from `pixgen.config.models`.
- Adds `Settings.groups: Mapping[str, ModelGroup]` with an empty mapping by default.
- `ModelGroup.models` is `tuple[ModelId, ...]` with at least one item.
- `ModelGroup.description` is a non-empty string after whitespace validation.
- `ModelGroup.tags` is `tuple[str, ...]`, defaulting to an empty tuple.

- [ ] **Step 1: Write failing configuration tests**

  Add tests with these names and assertions:

  - `test_model_group_accepts_models_description_and_tags` constructs a group from lists and asserts Pydantic converts them to tuples while preserving order.
  - `test_model_group_defaults_tags_to_empty` asserts `tags == ()`.
  - `test_model_group_rejects_empty_models` asserts validation fails for no models.
  - `test_model_group_rejects_duplicate_models` asserts validation fails when the same model ID appears twice.
  - `test_model_group_rejects_blank_description` asserts validation fails for `"   "`.
  - `test_model_group_rejects_blank_or_padded_tags` asserts validation fails for `""`, whitespace-only tags, and tags with leading or trailing whitespace.
  - `test_settings_loads_groups_from_toml` writes a temporary config containing `[groups.product-hero]`, then asserts the group fields and model order.
  - `test_settings_without_groups_uses_empty_mapping` asserts a settings instance created without a config file has no groups.
  - `test_settings_rejects_unknown_group_fields` writes a group containing an extra key and asserts `load_settings()` raises `PixgenError` with `ErrorCode.INVALID_CONFIGURATION`.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run:

  ```bash
  uv run pytest tests/config/test_models.py -k "group" -v
  ```

  Expected: FAIL because `ModelGroup` and `Settings.groups` do not exist.

- [ ] **Step 3: Implement `ModelGroup` and `Settings.groups`**

  Define `ModelGroup` beside `Defaults` with `ConfigDict(frozen=True, extra="forbid")`. Add a model validator that rejects whitespace-only descriptions, a field validator that rejects empty or padded tags, and a model validator that rejects duplicate model IDs. Add `groups: Mapping[str, ModelGroup] = Field(default_factory=dict)` to `Settings` and export `ModelGroup` in `__all__`.

  Keep group names as exact TOML mapping keys. Do not normalise names or add a name field to `ModelGroup`. Let `ModelId` handle model-ID syntax and let the existing settings source/error mapping handle TOML and Pydantic failures.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run:

  ```bash
  uv run pytest tests/config/test_models.py -k "group" -v
  ```

  Expected: PASS.

- [ ] **Step 5: Commit the configuration model**

  ```bash
  git add src/pixgen/config/models.py tests/config/test_models.py
  git commit -m "feat: add model group configuration"
  ```

### Task 2: Resolve groups in the create CLI

**Files:**
- Modify: `src/pixgen/cli/image.py`
- Modify: `src/pixgen/cli/app.py`
- Test: `tests/cli/test_image.py`
- Test: `tests/cli/test_app.py`

**Interfaces:**
- `build_operation_app(operation, invoker, factories, groups: Mapping[str, ModelGroup] | None = None) -> App` accepts configured groups. Only the create branch uses them.
- `build_app(application, registry, factories, groups: Mapping[str, ModelGroup] | None = None) -> App` forwards the mapping to the create operation builder.
- The create command adds `group: str | None = None` and keeps `model: list[str] | None = None` in one Cyclopts `MutuallyExclusive` group.
- The private resolver raises `PixgenError(ErrorCode.INVALID_REQUEST, ...)` for a missing group and returns `tuple[ModelId, ...]` for a configured group.
- The command always constructs `SharedSelection(models=..., parameters=SharedImageParams())` for shared create selection. It does not pass an aspect ratio from the root command.

- [ ] **Step 1: Write failing parser and resolution tests**

  Add tests with these names and assertions:

  - `test_create_accepts_group` parses `create --group product-hero "A forest"` and asserts the bound `group` value.
  - `test_create_rejects_group_and_model_together` parses both options and asserts Cyclopts raises its mutual-exclusion error.
  - `test_edit_rejects_group` asserts `edit --group product-hero ...` raises `UnknownOptionError`.
  - `test_create_rejects_shared_aspect_ratio` asserts root `create --aspect-ratio 16:9 ...` raises `UnknownOptionError`.
  - `test_edit_keeps_shared_aspect_ratio` parses `edit --aspect-ratio 3:2 ...` and asserts the existing bound parameter remains `"3:2"`.
  - `test_create_resolves_group_models_before_invocation` builds the create app with a group, invokes the parsed command through a recording application, and asserts the captured `SharedSelection.models` equals the configured model tuple in TOML order.
  - `test_create_unknown_group_returns_invalid_request_without_invoking` invokes an unknown group through a recording application that fails if called, then asserts the outcome is rejected with `ErrorCode.INVALID_REQUEST`.
  - `test_create_without_group_keeps_default_selection_path` asserts a command without `--group` still passes `models=None`, allowing `ImageApplication` to resolve `defaults.image_create_models`.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run:

  ```bash
  uv run pytest tests/cli/test_image.py tests/cli/test_app.py -k "group or aspect_ratio" -v
  ```

  Expected: FAIL because the builders do not accept groups, the command does not define `--group`, and the shared create aspect-ratio parameter still exists.

- [ ] **Step 3: Implement group wiring and create-only resolution**

  Import `Group` and `validators` from Cyclopts, create a mutual-exclusion group for the shared create model and group parameters, and add the create-only `group` parameter. Preserve the current edit model and aspect-ratio behavior.

  In `cli.app`, add optional `groups` parameters with `None` defaults so existing direct builder tests remain valid. In `main`, pass `runtime.settings.groups` to `build_app`. In `cli.image`, resolve `group` before constructing `SharedSelection`; use `group.models` when present and leave `models=None` when no selection option is supplied. Raise `PixgenError(ErrorCode.INVALID_REQUEST, f"unknown model group: {name}")` for missing names so `@cli_command()` produces the normal `CommandResult` error envelope.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run:

  ```bash
  uv run pytest tests/cli/test_image.py tests/cli/test_app.py -k "group or aspect_ratio" -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run the full existing CLI and application tests**

  Run:

  ```bash
  uv run pytest tests/cli tests/application -v
  ```

  Expected: PASS. Existing tests that assert the old root create aspect-ratio option must be updated to the new contract; provider-native and edit aspect-ratio tests must remain green.

- [ ] **Step 6: Commit the CLI behavior**

  ```bash
  git add src/pixgen/cli/image.py src/pixgen/cli/app.py tests/cli/test_image.py tests/cli/test_app.py
  git commit -m "feat: select create models by group"
  ```

### Task 3: Document the TOML format and command usage

**Files:**
- Modify: `README.md`
- Modify: `pixgen.toml`

**Interfaces:**
- Documents the exact `[groups.<name>]` shape with `models`, `description`, and `tags`.
- Documents `pixgen create --group NAME PROMPT`.
- Removes shared root create examples that use `--aspect-ratio`.
- Keeps provider-native aspect-ratio examples and the shared edit aspect-ratio example accurate.

- [ ] **Step 1: Update the configuration and CLI documentation**

  Add a commented group example to `pixgen.toml` so it does not select a group by default. Update `README.md` to show a group-based multi-model create example, explain that groups are create-only, state that `--group` and `--model` cannot be combined, and describe `description` and `tags` as metadata reserved for future group presentation. Update the shared-command wording so it does not claim that create still accepts a shared aspect-ratio option.

- [ ] **Step 2: Review the rendered text and configuration syntax**

  Run:

  ```bash
  uv run python -c "import tomllib; tomllib.load(open('pixgen.toml', 'rb'))"
  git diff --check
  ```

  Expected: the TOML parses successfully and Git reports no whitespace errors.

- [ ] **Step 3: Commit the documentation**

  ```bash
  git add README.md pixgen.toml
  git commit -m "docs: document create model groups"
  ```

### Task 4: Run repository verification

**Files:**
- No product files. This task verifies the completed implementation.

- [ ] **Step 1: Run lint and formatting**

  Run:

  ```bash
  just lint
  ```

  Expected: Ruff check and format complete successfully. Review any formatting changes before continuing.

- [ ] **Step 2: Run type checking**

  Run:

  ```bash
  just type-check
  ```

  Expected: Pyrefly reports no errors.

- [ ] **Step 3: Run the full test suite**

  Run:

  ```bash
  just test
  ```

  Expected: all tests pass.

- [ ] **Step 4: Run the full hook suite**

  Run:

  ```bash
  just check
  ```

  Expected: all `prek` hooks pass. If hooks modify files, inspect the diff, run the affected tests again, and commit the intended changes.
