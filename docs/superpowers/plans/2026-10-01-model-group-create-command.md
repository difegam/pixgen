# Model Group Creation Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pixgen group create NAME` with explicit repeated model options and an interactive fuzzy multi-select flow that atomically writes validated groups to Pixgen TOML configuration.

**Architecture:** Keep group creation separate from image generation. A configuration repository will read and validate the current TOML, add one `ModelGroup`, serialise Pixgen’s supported settings without secrets, and publish atomically. A CLI group module will use the existing provider registry for model choices and a dependency-free Rich/stdlib selector for interactive selection.

**Tech Stack:** Python 3.14, Cyclopts, Rich, Pydantic, `tomllib`, pytest, Ruff, and Pyrefly.

**Spec:** `docs/superpowers/specs/2026-10-01-model-group-create-design.md`

## Global Constraints

- Use the dedicated `pixgen group create NAME` command; do not change image-generation command semantics.
- Support repeated `--model MODEL` options and preserve their order.
- Interactive selection is available only when no models are supplied and stdin/stdout are interactive.
- Fuzzy selection must use the existing Rich dependency and the standard library; do not add a runtime dependency.
  > **Addendum (2026-10-01):** this constraint was revisited and superseded — the hand-rolled `termios`/`tty` selector was replaced with `InquirerPy` (`inquirer.fuzzy` / `inquirer.confirm`) for a more polished interactive UI. See the InquirerPy evaluation plan for details.
- Group fields written to TOML are only `models`, `description`, and `tags`.
- Validate selected models against `ProviderRegistry` before writing.
- Reject duplicate group names; never silently replace or merge an existing group.
- Preserve existing `defaults` and `generation` settings and never write credentials or secrets.
- Write configuration through a sibling temporary file followed by an atomic rename.
- Keep group metadata out of image-generation requests and provider construction.
- Use frozen Pydantic models, British English docstrings, and Google-style docstrings.
- Use `uv run pytest`, `just lint`, `just type-check`, and `just test`; the type checker is Pyrefly.
- Preserve unrelated working-tree changes and add only task-specific files to commits.

## Review Focus

- A valid group added to an existing config must preserve unrelated settings and existing groups; pin this in `tests/config/test_writer.py::test_create_group_preserves_existing_settings`.
- A duplicate group name must leave the file byte-for-byte unchanged; pin this in `tests/config/test_writer.py::test_create_group_rejects_existing_name_without_writing`.
- A syntactically valid but unregistered model must be rejected before writing; pin this in `tests/cli/test_group.py::test_create_group_rejects_unknown_model_without_writing`.
- A non-interactive invocation without `--model` must not read stdin or hang; pin this in `tests/cli/test_group.py::test_create_group_requires_models_when_noninteractive`.
- Fuzzy filtering must be deterministic for exact, prefix, substring, and no-match queries; pin this in `tests/cli/test_selector.py::test_fuzzy_rank_orders_matches_deterministically`.

## File Structure

- Create `src/pixgen/config/writer.py` for validated read/modify/serialise/atomic-write behavior.
- Create `src/pixgen/cli/selector.py` for fuzzy ranking, selector state, and interactive model selection protocols.
- Create `src/pixgen/cli/group.py` for the Cyclopts `group create` command and command-level orchestration.
- Modify `src/pixgen/core/results.py` and `src/pixgen/cli/outcome.py`/`src/pixgen/cli/render.py` for a small structured creation result that reports only the group name and config path.
- Modify `src/pixgen/cli/app.py` to register the group sub-app and inject the registry/repository/selector.
- Add `tests/config/test_writer.py`, `tests/cli/test_selector.py`, and `tests/cli/test_group.py`; extend `tests/cli/test_app.py` for root command registration.
- Modify `README.md` and `pixgen.toml` with the creation examples and metadata rules.

### Task 1: Add the configuration repository and TOML writer

**Files:**
- Create: `src/pixgen/config/writer.py`
- Test: `tests/config/test_writer.py`
- Reuse: `src/pixgen/config/models.py`, `src/pixgen/config/paths.py`, `src/pixgen/artifacts.py`

**Interfaces:**
- Produce `ConfigRepository(path: Path)`.
- Produce `ConfigRepository.create_group(name: str, group: ModelGroup) -> None`.
- Produce a private deterministic serializer for the supported `Settings` shape.
- Raise `PixgenError` with existing Pixgen error codes for invalid configuration and filesystem failures.

- [ ] **Step 1: Write failing repository tests**

  Add tests covering:

  - creating a group in a missing file creates parent directories and writes `[groups.<name>]`;
  - `test_create_group_preserves_existing_settings` retains defaults, generation values, and existing groups;
  - model order, description, and tags are serialised in the expected TOML shape;
  - `test_create_group_rejects_existing_name_without_writing` asserts the file bytes do not change;
  - malformed existing TOML fails before publication;
  - a write failure does not leave the final file partially replaced;
  - serialised output contains no API-key fields.

- [ ] **Step 2: Run the focused tests and confirm meaningful failure**

  Run:

  ```bash
  uv run pytest tests/config/test_writer.py -v
  ```

  Expected: FAIL because `ConfigRepository` does not exist.

- [ ] **Step 3: Implement `ConfigRepository`**

  Parse an existing file with `tomllib`, validate the resulting mapping with
  `Settings.model_validate`, reject an existing name, create a validated copy
  with the new group, and serialise only Pixgen’s supported non-secret fields.
  Use `write_atomic(path, encoded_text, overwrite=True)` after all validation
  succeeds. Quote group keys safely and encode strings/arrays deterministically;
  omit optional `None` values such as `run_timeout_seconds`.

- [ ] **Step 4: Run the focused tests and confirm green**

  Run:

  ```bash
  uv run pytest tests/config/test_writer.py -v
  ```

  Expected: PASS.

- [ ] **Step 5: Commit the repository component**

  ```bash
  git add src/pixgen/config/writer.py tests/config/test_writer.py
  git commit -m "feat: write model groups to config"
  ```

### Task 2: Add deterministic fuzzy selection and interactive state

**Files:**
- Create: `src/pixgen/cli/selector.py`
- Test: `tests/cli/test_selector.py`
- Reuse: `src/pixgen/core/models.py`, `src/pixgen/providers/registry.py`, Rich console primitives

**Interfaces:**
- Produce `InteractiveGroupSelection` containing selected model IDs, description, and tags.
- Produce `ModelSelector` as a runtime-checkable protocol with `select(models: tuple[ModelSpec, ...]) -> InteractiveGroupSelection`.
- Produce `fuzzy_rank(query: str, model: ModelSpec) -> tuple[int, int]` or an equivalent deterministic public test seam.
- Produce `InteractiveModelSelector.select(models: tuple[ModelSpec, ...]) -> InteractiveGroupSelection`.

- [ ] **Step 1: Write failing selector tests**

  Add tests covering:

  - `test_fuzzy_rank_orders_matches_deterministically` with exact, prefix,
    ordered-substring, and no-match inputs;
  - filtered model display uses canonical IDs and preserves registry order for
    equal scores;
  - selected model toggles preserve display order and reject empty selection;
  - metadata prompt returns the required description and trimmed tag values;
  - a fake selector can return a complete `InteractiveGroupSelection` without
    terminal control sequences.

- [ ] **Step 2: Run the focused tests and confirm meaningful failure**

  Run:

  ```bash
  uv run pytest tests/cli/test_selector.py -v
  ```

  Expected: FAIL because the selector interfaces do not exist.

- [ ] **Step 3: Implement selector state and terminal adapter**

  Keep fuzzy ranking and selection state pure and separately testable. Render
  the active query and checkbox rows with Rich. Use standard-library terminal
  input for arrow navigation, Space toggling, and Enter confirmation when raw
  terminal input is available; use a line-oriented prompt fallback for dumb or
  non-raw terminals. Prompt for the required description and optional tags only
  after a non-empty model selection.

- [ ] **Step 4: Run the focused tests and confirm green**

  Run:

  ```bash
  uv run pytest tests/cli/test_selector.py -v
  ```

  Expected: PASS.

- [ ] **Step 5: Commit the selector component**

  ```bash
  git add src/pixgen/cli/selector.py tests/cli/test_selector.py
  git commit -m "feat: add interactive model group selector"
  ```

### Task 3: Add the structured group-create result and command

**Files:**
- Create: `src/pixgen/cli/group.py`
- Modify: `src/pixgen/core/results.py`
- Modify: `src/pixgen/cli/outcome.py`
- Modify: `src/pixgen/cli/render.py`
- Test: `tests/cli/test_group.py`

**Interfaces:**
- Produce `GroupCreateResult` with schema version `"1"`, `name`, `config_path`, and optional `PublicError`.
- Produce `build_group_app(registry: ProviderRegistry, repository: ConfigRepository, selector: ModelSelector | None = None) -> App`.
- Register `create(name, *, model: list[str] | None, description: str | None, tag: list[str] | None, json: bool = False) -> CliOutcome`.
- Preserve the existing `CliOutcome`/`RESULT_ACTION` error and exit-status conventions.

- [ ] **Step 1: Write failing command tests**

  Add tests covering:

  - explicit repeated `--model` options preserve order in the written group;
  - explicit creation requires a non-blank description and accepts repeated tags;
  - `test_create_group_rejects_unknown_model_without_writing` confirms the
    repository and selector are not called;
  - interactive creation delegates to the injected selector and writes its
    selected models/metadata;
  - `test_create_group_requires_models_when_noninteractive` rejects an omitted
    model list without calling stdin;
  - duplicate group names return `invalid_request` and do not write;
  - `--json` renders only the group name and config path, not description/tags;
  - command errors use the existing `CliOutcome` rejection path.

- [ ] **Step 2: Run the focused tests and confirm meaningful failure**

  Run:

  ```bash
  uv run pytest tests/cli/test_group.py -v
  ```

  Expected: FAIL because the result type and group app do not exist.

- [ ] **Step 3: Implement result, renderer, and command orchestration**

  Add the frozen result model and renderer branch. In `group.py`, resolve
  explicit model IDs through `registry.get_model`, reject duplicates before
  invoking the repository, require a description for explicit mode, and use
  the injected selector only for interactive mode. Construct `ModelGroup`, call
  `repository.create_group`, and return a success result containing only the
  group name and resolved config path. Wrap expected Pixgen/Pydantic failures
  with the existing command decorator.

- [ ] **Step 4: Run the focused tests and confirm green**

  Run:

  ```bash
  uv run pytest tests/cli/test_group.py -v
  ```

  Expected: PASS.

- [ ] **Step 5: Commit the command component**

  ```bash
  git add src/pixgen/cli/group.py src/pixgen/core/results.py src/pixgen/cli/outcome.py src/pixgen/cli/render.py tests/cli/test_group.py
  git commit -m "feat: add group create command"
  ```

### Task 4: Register the command in the root app and document it

**Files:**
- Modify: `src/pixgen/cli/app.py`
- Test: `tests/cli/test_app.py`
- Modify: `README.md`
- Modify: `pixgen.toml`

**Interfaces:**
- `build_app(...)` registers `build_group_app(...)` with the existing registry and a repository rooted at `resolve_config_path()`.
- Existing image and model command registration remains unchanged.

- [ ] **Step 1: Write failing root-registration tests**

  Add tests asserting:

  - `group create` appears in the root parser;
  - the root app can parse repeated models and description/tag options;
  - image `create --group` and `create --model` mutual exclusion remains unchanged;
  - `edit` still rejects `--group`;
  - building the root app does not require API credentials or invoke provider clients.

- [ ] **Step 2: Run the focused tests and confirm meaningful failure**

  Run:

  ```bash
  uv run pytest tests/cli/test_app.py -k "group" -v
  ```

  Expected: FAIL because the root app does not register the group sub-app.

- [ ] **Step 3: Register the group app**

  Add optional dependency injection parameters only where needed for tests;
  production `main()` should pass the existing registry and a repository using
  `resolve_config_path()`. Do not pass API keys into the repository or selector.

- [ ] **Step 4: Update documentation and sample config**

  Document both explicit and interactive forms, the required explicit
  description, repeated tags, create-only scope, duplicate-name behavior, and
  the fact that metadata is reserved for future `group list`/`group show`.
  Add a commented `[groups]` example to `pixgen.toml` without changing runtime
  defaults.

- [ ] **Step 5: Run root tests and validate documentation syntax**

  Run:

  ```bash
  uv run pytest tests/cli/test_app.py -k "group" -v
  uv run python -c "import tomllib; tomllib.load(open('pixgen.toml', 'rb'))"
  git diff --check
  ```

  Expected: PASS, valid TOML, and no whitespace errors.

- [ ] **Step 6: Commit root wiring and documentation**

  ```bash
  git add src/pixgen/cli/app.py tests/cli/test_app.py README.md pixgen.toml
  git commit -m "feat: register model group creation"
  ```

### Task 5: Run repository verification

**Files:**
- No planned product changes; inspect any formatter or hook edits before committing them.

- [ ] **Step 1: Run the affected suites**

  ```bash
  uv run pytest tests/config tests/cli -v
  ```

- [ ] **Step 2: Run formatting and linting**

  ```bash
  just lint
  ```

- [ ] **Step 3: Run Pyrefly**

  ```bash
  just type-check
  ```

- [ ] **Step 4: Run the full test suite**

  ```bash
  just test
  ```

- [ ] **Step 5: Run the full hook suite**

  ```bash
  just check
  ```

- [ ] **Step 6: Review the final diff and status**

  Confirm only intended feature commits/files changed and the pre-existing
  unrelated files remain untouched. If any verification command modifies a
  feature file, rerun the affected tests and commit only the intended changes.
