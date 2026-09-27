# Provider-owned CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `--param` and the `image` command group with provider-owned typed commands and strict shared aspect-ratio support.

**Architecture:** Root `create` and `edit` apps have shared default commands and provider-owned sub-apps. Provider definitions compose native Pydantic parameters, restrictions, and predefined ratio mappings. Shared and native commands converge on typed requests and the existing image orchestration pipeline.

**Tech Stack:** Python 3.14, Pydantic 2, Cyclopts 4.25.2 or the repository-locked compatible version, pytest, pyrefly, Ruff, uv, just, prek.

**Spec:** [Approved design](../specs/2026-09-27-provider-owned-cli-design.md)

## Global Constraints

- Pixgen supports image-generation providers only, including image editing.
- Shared generation parameters contain only optional `aspect_ratio`; omission preserves provider/model defaults.
- Remove the `image` command group and `--param`; do not retain compatibility aliases.
- Native commands select one provider-local model using required `--model`; shared commands retain repeated canonical IDs and configured default model lists.
- All selected targets pass preflight before any generation/network work; unsupported ratios never fall back to another ratio, resizing, or cropping.
- Model-specific parameter logic stays inside provider packages. Main CLI imports no concrete providers; core has no I/O or Cyclopts.
- Retain output planning, atomic writes, variants, timeouts, and partial-failure behaviour.
- Frozen Pydantic models, forbidden extras for parameter models, British English Google-style docstrings, and modern annotations. Follow `.agents/skills/python-style/SKILL.md`; explicit Cyclopts requirements supersede its generic argparse default.
- Tests use fakes, temporary files, and no real network or credentials. `asyncio_mode = "auto"`; no asyncio decorators.
- Complete `just lint && just type-check && just test` before implementation completion. Type checking uses pyrefly, hooks use prek.
- Preserve existing uncommitted work. Read the current checkout again at execution time; do not replace files with versions from HEAD.

## Review Focus

- An equivalent ratio such as `21:9` canonicalises to `7:3`, but Gemini must still receive its native `21:9` spelling. Task 2 pins this.
- A native parameter explicitly supplied at its default value must still fail when unsupported by the selected model. Track explicitly supplied fields before dumping. Task 4 pins this.
- Frozen Pydantic models do not recursively freeze dictionaries. Definition construction must detach caller-owned mappings so mutations cannot alter registered capabilities. Task 1 pins this.
- A provider command name used as the complete prompt must remain expressible through `--prompt` and `--`. Task 5 pins this.
- Concrete native fields must survive storage behind a shared request interface and serialization without a central union of providers. Tasks 3 and 4 pin this.

## File structure

| Files | Responsibility |
|---|---|
| `src/pixgen/core/aspect_ratio.py` | Canonical textual ratio type and validation |
| `src/pixgen/core/parameters.py` | Shared parameters and frozen native parameter base |
| `src/pixgen/core/definitions.py` | Generic model/operation definitions and pure conversion |
| `src/pixgen/core/requests.py` | Typed shared/native selections and validated request envelope |
| `src/pixgen/core/params.py` | Delete when the raw parser is retired |
| `src/pixgen/providers/openai/{__init__,parameters,definitions,adapter,cli}.py` | Split existing OpenAI module by responsibility, retaining public provider import |
| `src/pixgen/providers/gemini/{__init__,parameters,definitions,adapter,cli}.py` | Equivalent Gemini package |
| `src/pixgen/providers/base.py`, `registry.py` | Provider protocol, prepared requests, registration and lookup |
| `src/pixgen/application.py` | Typed preflight and existing execution |
| `src/pixgen/cli/contracts.py`, `options.py`, `invoke.py` | CLI factory protocol, reusable options, rendering/execution service |
| `src/pixgen/cli/image.py`, `app.py` | Generic operation-app builders and root mounting; internal filename may remain image-specific |
| `src/pixgen/cli/model.py`, `render.py`, `core/results.py` | Shared-capability introspection |
| `src/pixgen/runtime.py` | Inject provider adapters and CLI factories |
| `tests/core/`, `tests/providers/`, `tests/application/`, new `tests/cli/` | Tests at the corresponding contract boundaries |
| `tests/factories.py`, `tests/test_runtime.py`, `README.md` | Reusable fakes, runtime coverage, migration examples |

The provider module-to-package split belongs to Task 2, not an independent cleanup. Preserve existing constructor injection and public `OpenAIProvider`/`GeminiProvider` imports.

## Before execution

- [ ] Read the approved spec, current AGENTS.md, Python conventions, and repository TDD workflow. Inspect `git status --short`, staged changes, and current tests before editing.
- [ ] Use the worktree skill to assess isolation. The spec explicitly depends on the uncommitted checkout: a new worktree starting from HEAD alone is insufficient. Preserve or transfer the complete baseline if isolation is used; do not discard, commit indiscriminately, or silently omit it.
- [ ] Run `just lint && just type-check && just test` as a baseline. Inspect formatter changes separately. Record pre-existing failures; do not call them regressions or broaden this feature to fix unrelated issues without explaining the dependency.

For every task below, complete red, green, and affected-suite verification per behaviour before moving to the next behaviour. Commits include only that task's reviewed changes; use selective staging where files already contained user edits.

### Task 1: Define canonical ratios and composed model data

**Files:** Create `core/aspect_ratio.py`, `core/parameters.py`, `core/definitions.py`; create `tests/core/test_aspect_ratio.py`, `tests/core/test_definitions.py`; extend `tests/factories.py`.

**Interfaces:**
- `normalise_aspect_ratio(value: str) -> str` and a Pydantic-compatible `AspectRatio` annotated string type.
- `ProviderParams(BaseModel)`: frozen, forbidden extras, no generation fields.
- `SharedImageParams(BaseModel)`: frozen, forbidden extras; `aspect_ratio: AspectRatio | None = None`.
- `OperationDefinition[P: ProviderParams]`: `parameter_type: type[P]`, `defaults: P`, `media: Mapping[MediaRole, MediaRoleSpec]`, `aspect_ratios: Mapping[AspectRatio, JsonObject]`.
- `OperationDefinition.resolve(shared: SharedImageParams) -> P`: merge only the mapped override into defaults and validate through `parameter_type`; unsupported ratio raises `ValueError` for the provider boundary to contextualise.
- `ModelDefinition[P: ProviderParams]`: `spec: ModelSpec`, `operations: Mapping[ImageOperation, OperationDefinition[P]]`; validate declared operation/media agreement with the public spec.

Definitions remain pure data plus pure validation. Exclude class objects from public catalogue output. Copy incoming mappings and nested override dictionaries; do not expose mutation as a supported capability-editing API. Validate defaults against their declared parameter type and every mapped payload merged with defaults at construction.

- [ ] Add parametrised `TestAspectRatio` tests asserting `32:18 -> 16:9`, `2:2 -> 1:1`, `21:9 -> 7:3`, and `7:5 -> 7:5`. Reject `0:1`, `-1:2`, `1.5:1`, `16/9`, `1:`, `:1`, `1:2:3`, empty strings, and whitespace inside components. Require ASCII decimal digits; surrounding whitespace is rejected. Leading zeros are accepted and canonicalised.
- [ ] Run `uv run pytest tests/core/test_aspect_ratio.py -v`; confirm missing behaviour produces failure.
- [ ] Implement the ratio type and shared/native parameter bases. Use a bounded-scope regex check plus integer GCD normalisation; no provider enum.
- [ ] Run the same test target and confirm all cases pass.
- [ ] Add `TestOperationDefinition` tests: omission returns default values; matching ratio changes only mapped fields; unsupported ratio fails; invalid native override fails at construction; canonical-key collisions such as `16:9` and `32:18` fail rather than overwrite. Add a test mutating the input dictionary after construction and assert the definition remains unchanged. Add operation/media consistency tests for `ModelDefinition`.
- [ ] Run `uv run pytest tests/core/test_definitions.py -v`, observe red, implement composed definitions, then rerun to green.
- [ ] Run `uv run pytest tests/core/test_aspect_ratio.py tests/core/test_definitions.py -v` and `just type-check`.
- [ ] Commit the focused data-contract changes as `feat: define shared ratios and composed model definitions`.

### Task 2: Move provider schemas and conversion maps into definitions

**Files:** Replace `providers/openai.py` and `providers/gemini.py` with the packages listed above, initially without CLI modules. Modify `tests/providers/test_openai.py`, `test_gemini.py`; create `tests/providers/test_definitions.py`.

**Interfaces:**
- Both providers add `definitions() -> tuple[ModelDefinition[...], ...]`, with their concrete native parameter types. Preserve existing `models()` as the public `ModelSpec` projection.
- Expose typed definitions from each provider's `definitions.py`; existing catalogue constants remain public projections if existing callers need them.
- `OpenAIParams`, `GeminiParams`, and `GeminiLiteParams` extend `ProviderParams`. Operation definitions bind concrete models, including the Lite restriction.
- `parameter_schema(model: ModelId, operation: ImageOperation) -> JsonSchema` delegates to the exact operation definition, with unknown model/operation errors instead of fallback.

- [ ] Add mapping tests for every row in the spec's OpenAI table for both operations. Assert Mini rejects `16:9` and `7:3`; GPT Image 2 resolves `16:9` to `1536x864` and `7:3` to `1792x768`. Assert omission does not add a `size` value.
- [ ] Run `uv run pytest tests/providers/test_definitions.py -v` and confirm the new definitions are missing.
- [ ] Split provider modules, preserve constructor and adapter behaviour, and implement OpenAI definitions using the exact spec table. Keep all conversion values in provider code. Restrict Mini native size values to its documented supported presets; validate GPT Image 2 mapped dimensions against its documented bounds.
- [ ] Add Gemini tests asserting canonical `7:3` resolves to native `21:9`, other approved ratios map directly, and omitted shared ratio/image size remains omitted. Assert Lite still rejects `image_size="2K"` and introspection advertises its narrower schema. Assert unknown model IDs and unsupported operations do not reuse another model's schema.
- [ ] Run those tests to red, implement the Gemini definitions, then rerun to green. Reuse definitions instead of maintaining the existing separate parameter-class switch and duplicate size restriction table.
- [ ] Run `uv run pytest tests/providers -v` and `just type-check`; account for explicit field presence when applying model-specific native restrictions.
- [ ] Commit as `refactor: compose provider model schemas and ratio mappings`.

### Task 3: Carry typed selections through strict orchestration

**Files:** Modify `core/requests.py`, `providers/base.py`, both provider adapters, `providers/registry.py`, `application.py`, `cli/image.py`; delete `core/params.py`; modify request/application/provider tests and delete obsolete parser tests in `tests/core/test_params.py`.

**Interfaces:**
- `SharedSelection`: frozen model with `models: tuple[ModelId, ...] | None` and `parameters: SharedImageParams`.
- `NativeSelection`: frozen model with `model: ModelId` and `parameters: SerializeAsAny[ProviderParams]`.
- `ParameterSelection = SharedSelection | NativeSelection`.
- `ValidatedImageRequest[P: ProviderParams]`: intent and model metadata as before, `parameters: P`; use `SerializeAsAny` at erased storage boundaries so concrete fields survive without a global provider union.
- Provider `prepare_shared(*, intent: ImageIntent, model: ModelId, parameters: SharedImageParams) -> ValidatedImageRequest[ProviderParams]` and `prepare_native(*, intent: ImageIntent, model: ModelId, parameters: ProviderParams) -> ValidatedImageRequest[ProviderParams]`. Returned instances are concretely parameterised internally. Model/operation lookup and validation remain provider-owned.
- `ImageApplication.run(intent: ImageIntent, *, selection: ParameterSelection | None = None, variants: int = 1, output: Path | None = None, output_dir: Path | None = None, mkdir: bool = False, force: bool = False, timeout_seconds: int | None = None) -> RunOutcome`.
- No selection means shared defaults. Remove `raw_params`, the separate `models` argument, and `intent.params`. Update callers in this task so intermediate code remains callable.

- [ ] Add `TestTypedRequests` tests using a fake native model with a field absent from `ProviderParams`; assert validation and `model_dump()` preserve it through `NativeSelection` and prepared requests. Assert wrong native parameter types cannot bypass selected-model validation. Observe red with `uv run pytest tests/core/test_requests.py -v`.
- [ ] Implement typed selections/requests and provider preparation methods. Validate native fields using explicit-field information plus selected defaults, so unsupported explicit fields are rejected even if their value equals a broad schema default. Serialise payloads only within adapters using native aliases and omission of absent values.
- [ ] Add application tests for a compatible two-model ratio and an incompatible second model. Assert exit code 2, error identifies the model/operation/ratio and supported ratios, every fake provider has zero generate/client-factory calls, and no output artifacts or requested output directory were created.
- [ ] Add tests showing omitted ratio preserves defaults, duplicate model IDs still fail, missing edit inputs still fail, shared ratios obey edit restrictions, and native requests run through the same preflight. Observe red using `uv run pytest tests/application/test_application.py -v`.
- [ ] Replace raw parameter parsing with selection preparation. Validate all selected native requests before output-directory creation and generation. Keep local media checks, job execution, deadlines, and partial-result logic intact. Update the existing CLI temporarily to construct `SharedSelection` with `--aspect-ratio`; remove `--param` now.
- [ ] Replace obsolete raw-parser tests with public typed-selection behaviour tests; update existing fixtures and adapter payload assertions rather than deleting equivalent coverage.
- [ ] Run `uv run pytest tests/core tests/providers tests/application tests/test_artifacts.py -v` and `just type-check`.
- [ ] Commit as `refactor: preflight typed image requests across models`.

### Task 4: Define provider CLI factories and shared invocation helpers

**Files:** Create `cli/contracts.py`, `cli/options.py`, `cli/invoke.py`, provider `cli.py` modules, `tests/cli/__init__.py`, `tests/cli/test_provider_commands.py`; modify `tests/factories.py`.

**Interfaces:**
- `ExecutionOptions`: frozen Pydantic model for existing variants, output/output_dir, timeout_seconds, mkdir, force, and JSON options, retaining their CLI spellings/defaults.
- `CommandInvoker(application: ImageApplication)` with `async shared(intent: ImageIntent, selection: SharedSelection, options: ExecutionOptions) -> None` and `async native(intent: ImageIntent, selection: NativeSelection, options: ExecutionOptions) -> None`. Both render once and exit using the application's outcome.
- Runtime-checkable `ProviderCliFactory` protocol: `name: str`, `operations: frozenset[ImageOperation]`, `build(operation: ImageOperation, invoker: CommandInvoker) -> App`.
- `OpenAICliFactory` and `GeminiCliFactory` implement that protocol in their own packages. Returned apps are named `openai` and `gemini`, with a default command whose native Pydantic fields are flattened into ordinary flags.

Cyclopts annotations must resolve at runtime even with postponed annotations. Use the installed Pydantic/Cyclopts integration; consult Context7 if annotation/alias handling differs. Do not manually duplicate each native field in the main CLI or generate flags from a central provider union.

- [ ] Add parser tests asserting OpenAI accepts `--quality high --size 1536x1024`, Gemini accepts `--image-size 2K --aspect-ratio 16:9`, and each rejects the other's unsupported native flags. Assert required provider-local `--model` and rejection of a foreign provider model.
- [ ] Run `uv run pytest tests/cli/test_provider_commands.py -v` to observe red.
- [ ] Implement the factory protocol, common options and invocation service, then provider-native apps. Prompt and input paths construct the existing operation-specific intents; native options construct typed selections. Native errors must use the established rendering/exit conventions; the broad CLI schema must not override the selected model's restrictions.
- [ ] Add tests that Mini rejects explicitly supplied unsupported size and Lite rejects `--image-size 2K` before any generation. Add a fake provider with an optional broad field whose default is rejected for a narrower model: explicit default-value input must fail; omission must preserve selected defaults. Add an OpenAI payload assertion that compression value `0` survives CLI parsing and serialization.
- [ ] Observe red for each restriction/presence case, implement the minimal correction, and rerun `uv run pytest tests/cli/test_provider_commands.py tests/providers -v` to green.
- [ ] Verify native help lists schema fields and descriptions, common execution flags remain available, and constructing/helping apps does not create clients. Run `just type-check`.
- [ ] Commit as `feat: expose provider-owned typed image commands`.

### Task 5: Mount root operations and verify registration extensibility

**Files:** Modify `cli/image.py`, `cli/app.py`, `runtime.py`, `providers/registry.py`; create `tests/cli/test_app.py`; extend `tests/providers/test_registry.py`, `tests/test_runtime.py`, `tests/factories.py`.

**Interfaces:**
- `build_operation_app(operation: ImageOperation, invoker: CommandInvoker, factories: tuple[ProviderCliFactory, ...]) -> App` returns root-ready `create` or `edit` app, with shared default handler and matching provider sub-apps.
- `build_app(application: ImageApplication, registry: ProviderRegistry, factories: tuple[ProviderCliFactory, ...]) -> App` mounts operation apps plus existing `model` app.
- `ProviderRegistry.providers() -> tuple[ImageProvider, ...]` enables generic factory validation; constructor validates unique provider names, canonical model IDs and model ownership.
- Replace the runtime tuple with `Runtime` containing `application`, `registry`, `settings`, and `cli_factories`; `build_runtime() -> Runtime`. `main()` consumes these fields.

- [ ] Add root parser tests for `create`, `edit`, native provider subcommands, repeated shared `--model`, default model lists, `--prompt openai`, and `-- openai`. Assert `image create` and `--param` fail, and root help lists create/edit/model without image.
- [ ] Run `uv run pytest tests/cli/test_app.py -v`, confirm red, then implement root mounting with Cyclopts default handlers. Preserve factory input order and deterministic help.
- [ ] Add registry tests for duplicate names/IDs and a model whose canonical provider prefix disagrees with its owner. Add assembly tests for duplicate CLI names, missing CLI factory, unknown factory provider, and factory operations differing from provider definitions. Observe red, implement deterministic registration errors before serving CLI calls, rerun to green.
- [ ] Add a fake image provider named `example`, local model `demo`, native parameter `colour`, and a CLI factory via test factories. Assemble through the same registry/factory interfaces and assert `create example ... --model demo --colour blue` works, shared mapped ratio preparation works, and catalogue includes `example/demo`, without changes to production CLI assembly.
- [ ] Assert factory calls return fresh apps for repeated builds, and repeated builds do not duplicate commands. Cover a create-only provider: no edit sub-app is mounted and shared edit selection fails preflight. Implement any registration corrections after observing failures.
- [ ] Update runtime composition to register real adapters and factories. Run `uv run pytest tests/cli tests/providers/test_registry.py tests/test_runtime.py -v` and `just type-check`; verify help/catalogue still require neither credentials nor clients.
- [ ] Commit as `feat: mount image operations and provider apps at root`.

### Task 6: Publish capabilities, migration documentation, and final validation

**Files:** Modify `core/results.py`, `cli/model.py`, `cli/render.py`, `README.md`, `tests/core/test_results.py`; create `tests/cli/test_model.py`; review all touched files.

**Interfaces:**
- Add `ModelGetResult.shared_aspect_ratios: dict[str, tuple[str, ...]]`, keyed by existing operation values and containing canonical supported ratios.
- Native JSON parameter schemas come from the selected operation's concrete parameter type. Public `ModelSpec` metadata remains unchanged; no class/client objects enter results.

- [ ] Add catalogue JSON/human-output tests asserting both native schemas and canonical ratio lists. Check Mini lacks `16:9`, Gemini reports `7:3` while native schema uses `21:9`, and Lite schema restricts image size to `1K`. Check unknown model errors and JSON serialisability.
- [ ] Run `uv run pytest tests/cli/test_model.py tests/core/test_results.py -v` to observe red. Implement introspection/result rendering and rerun to green.
- [ ] Update README commands to root create/edit syntax. Replace `--param` recipes with shared `--aspect-ratio` or native provider flags; document required native model, defaults, strict failure, prompt disambiguation, and canonical ratio/native spelling differences. Describe mapping-selected sizes without promising identical resolution across models.
- [ ] Search active source and README using `rg -n -- '--param|pixgen image|raw_params|parse_params' src README.md`. Expected: no obsolete active API/examples; historical specs/plans and rejection tests may retain old spellings.
- [ ] Run `just lint && just type-check && just test`. All must pass. Inspect the resulting diff for unrelated edits and preserve baseline work. If a baseline failure remains, report it explicitly and do not claim a fully passing suite.
- [ ] Run offline smoke checks: `uv run pixgen --help`, `uv run pixgen create --help`, `uv run pixgen create openai --help`, `uv run pixgen edit gemini --help`, `uv run pixgen model list --json`, and `uv run pixgen model get gemini/gemini-3.1-flash-lite-image --json`. Expected: correct commands/options and JSON, no generation/network requests.
- [ ] Review the fake-provider extension test and actual import graph: no concrete provider imports or native parameter branches in main CLI, no Cyclopts/I/O in core, and no network client creation during app construction.
- [ ] Commit as `docs: document typed commands and shared ratio capabilities`, including the validated introspection changes. Complete the selected execution method's review and branch handoff; do not merge or publish implicitly.

## Plan self-review

The six tasks cover the approved root command layout, composed definitions, ratio mappings, strict preflight, typed native parameters, provider factories, offline introspection, and removal/migration of the old interface. Review-focus conditions have named tests in their owning tasks. The implementation remains image-specific and adds no providers or shared options beyond aspect ratio.

No implementation work is authorised by this plan's existence alone. The user reviews it and selects the execution method before implementation starts.
