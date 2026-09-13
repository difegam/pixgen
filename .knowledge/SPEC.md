# Specification

## Objective

Implement the PixGen MVP: a local BYOK CLI through which a developer or
coding agent discovers models and generates images/videos across Google,
OpenAI, Runway, and fal through one stable command and JSON contract.

## Scope

Only the MVP in `PROJECT.md`.

## Out of scope

Deferred capabilities in `IDEA.md`, including audio/voice, 3D, workflow
orchestration, local inference, MCP, automatic routing/fallback, social
publishing, hosted services, and creative web studios.

## Functional requirements

- **FR-001 --- Distribution:** expose `pixgen`; support
    `uv tool install pixgen` and `uvx pixgen`.
- **FR-002 --- Global CLI:** help/version; application-data commands
    support `--json`; JSON has no decorative formatting.
- **FR-003 --- Providers:** `provider list/get` reports installed
    providers, supported media kinds, and credential presence/source
    without values.
- **FR-004 --- Built-ins:** Google, OpenAI, Runway, fal.
- **FR-005 --- Models:** `model list/get` supports provider/kind
    filtering and exposes capabilities, accepted media
    roles/cardinality, and known constraints.
- **FR-006 --- Model IDs:** generic models use unambiguous
    provider-qualified identifiers.
- **FR-007 --- Image:** `image create` accepts model, prompt,
    compatible references/options, wait behavior, and output path;
    submission persists a Generation.
- **FR-008 --- Video:** `video create` supports prompt, compatible
    reference/start frame, options, wait behavior, output path, and
    asynchronous APIs.
- **FR-009 --- Reference validation:** reject known-invalid media
    roles/counts before submission.
- **FR-010 --- Native parameters:** provide one documented
    provider-native parameter mechanism without turning them into global
    config.
- **FR-011 --- Wait:** create waits by default unless no-wait is
    requested; polling/timeout are finite; wait timeout leaves
    generation resumable.
- **FR-012 --- History:** every submitted remote generation gets a
    persistent immutable local ID and sanitized SQLite record.
- **FR-013 --- Inspect:** `generation get/list` exposes local state;
    list filters at least provider, kind, status, limit.
- **FR-014 --- Resume:** `generation wait <id>` reloads provider job
    identity, polls correct adapter, updates state, downloads artifacts.
- **FR-015 --- Cancel:** call provider cancellation when supported;
    otherwise stable unsupported-operation error.
- **FR-016 --- Artifacts:** completed downloadable media streams to
    requested local path and persists as Artifact.
- **FR-017 --- Download failure:** provider-completed state remains
    completed if only local artifact download fails.
- **FR-018 --- Paths:** PlatformDirs determines
    config/data/cache/state paths.
- **FR-019 --- Config:** non-secret YAML loads through Pydantic
    Settings using architecture precedence.
- **FR-020 --- Secret exclusion:** keys never persist in YAML, SQLite
    history, normal logs, JSON, info, or doctor.
- **FR-021 --- Keyring:** `keys set/list/delete`; set obtains secret
    without requiring it as a CLI argument.
- **FR-022 --- Env fallback:** provider env credential works when
    keyring entry/backend is absent.
- **FR-023 --- Credential precedence:** keyring beats provider
    environment variable.
- **FR-024 --- Plugins:** discover documented Python entry points;
    plugin may register provider, provider-scoped commands, doctor
    checks.
- **FR-025 --- Namespace:** plugin commands exist only under
    `provider <name>`.
- **FR-026 --- Duplicate provider:** deterministic error; never
    silently choose.
- **FR-027 --- Plugin introspection:** `plugins` lists
    distributions/version/provider/load failures.
- **FR-028 --- Plugin API version:** expose compatibility version;
    incompatible plugins fail clearly.
- **FR-029 --- Info:** passive `info` reports versions, resolved
    paths, keyring backend, credential env set/unset, providers/plugins;
    no provider generation requests.
- **FR-030 --- Root doctor:** only generic diagnostics entry is
    `pixgen doctor`; aggregates core/provider/plugin checks; supports
    JSON.
- **FR-031 --- Doctor filter:** `doctor --provider` filters root
    checks; no nested provider doctor.
- **FR-032 --- Doctor checks:** config parse, writable dirs,
    SQLite/schema prerequisites, keyring availability, plugin loading,
    provider credential presence; network checks clearly identified.
- **FR-033 --- Errors:** versioned machine error with stable
    code/message/provider/retryable. Distinguish usage/request, auth,
    rate-limit, unavailable, timeout, unsupported, generation, plugin,
    storage/artifact failures.
- **FR-034 --- Exit status:** success 0; invalid usage/operational
    failure non-zero; documented mapping stable within major CLI
    version.
- **FR-035 --- Sanitization:** provider metadata passes core
    sanitization before persistence; no auth headers/keys/sensitive
    signed URLs.
- **FR-036 --- SQLite:** enable WAL, foreign keys, finite busy
    timeout.
- **FR-037 --- Migrations:** schema version + tested forward
    migrations; plugins own no core migrations.
- **FR-038 --- Claude Skill:** teach info/doctor, discovery,
    capability inspection, JSON, explicit project output paths, and
    resume by local ID; no secrets.
- **FR-039 --- Provider contracts:** shared mocked/fixture tests cover
    discovery metadata, translation, state normalization, error mapping,
    sanitization.
- **FR-040 --- Live tests:** billable/credentialed tests never run by
    default.

## Quality requirements

- **QR-001 Secret safety:** regression tests prove representative
    secrets absent from output/logs/history.
- **QR-002 Non-interactive:** all operations except explicit secret
    entry work without prompts after setup.
- **QR-003 Bounded network:** finite HTTP/polling timeouts; streamed
    artifact downloads.
- **QR-004 Portability:** CPython 3.12+ on macOS/Linux/Windows;
    environment credentials support headless systems.
- **QR-005 Plugin boundary:** only documented hooks/models are
    third-party compatibility API.

## Important scenarios

1. Claude discovers a Google image model, creates with `--json`,
    receives local path, and no secret leaks.
2. User submits async video no-wait, exits, later resumes with local
    generation ID and downloads result.
3. Two references supplied to a model known to allow one: fail before
    provider request.
4. Headless host has no keyring but valid provider env variable:
    generation works without secret persistence.
5. External fixture plugin appears in provider list, only owns its
    provider subcommands, and contributes root doctor check.
6. Provider completes but output directory is unwritable: Generation
    stays completed; artifact/storage failure is reported separately.

## Contracts

Generation states: `submitted`, `processing`, `completed`, `failed`,
`cancelled`. Local wait timeout is not a state.

Credential resolution: keyring → provider environment → missing
credentials.

Core owns root CLI, DB/migrations, credentials, common
request/result/error models. Provider plugins own provider
translation/catalog/native parameters/provider commands/doctor checks.

Every top-level JSON result/error has a schema version.

## Testing decisions

Test at CLI, core contract, real temporary SQLite, provider mock
transport/fixtures, entry-point fixture plugin, and separately marked
live-provider boundaries. No initial `QA.md`; reassess cross-platform
keyring and Claude Skill manual testing at release-candidate time.

## Acceptance criteria

- [ ] uv install and uvx invocation work.
- [ ] provider/model discovery works in human and JSON modes.
- [ ] four built-ins pass shared provider contracts.
- [ ] generic image generation downloads a supported image.
- [ ] async video survives process exit and resumes.
- [ ] known-invalid references fail locally.
- [ ] history persists across processes.
- [ ] completed generation and artifact failure remain distinct.
- [ ] keyring/env precedence works and secret regression tests pass.
- [ ] fixture provider registers without core change and cannot
    pollute root namespace.
- [ ] `info` is passive and secret-safe.
- [ ] one root `doctor` aggregates core/plugin/provider checks.
- [ ] SQLite uses WAL/foreign keys/finite busy timeout and migration
    tests pass.
- [ ] default tests make no billable requests.
- [ ] Claude Code follows shipped Skill to discover a model and create
    an artifact using shell access.

## Implementation sequence

### I1: Executable CLI foundation

Outcome: distributable root CLI with JSON/error envelope, help/version,
PlatformDirs paths, basic passive `info`, tests.

Depends on: none.

Validation: build succeeds; `uv run pixgen --help`; built wheel invokes
in isolated environment; CLI tests pass.

### I2: Configuration, credentials, and storage

Outcome: YAML preferences, keyring/env credential resolution, SQLite
Generation/Artifact persistence, migration and sanitization.

Depends on: I1.

Validation: precedence/keyring tests; SQLite round-trip/migration tests;
secret sentinel absent from persisted/output data.

### I3: Provider/plugin contract and discovery

Outcome: built-ins and fixture plugins register providers, provider
commands, and doctor checks through the small public contract.

Depends on: I1, I2.

Validation: fixture entry point loads; duplicate provider fails; command
only under `provider fixture`; doctor JSON contains fixture check.

### I4: First image vertical slice

Outcome: Google (after rechecking its current official API/model)
generates/downloads an image through final generic contract.

Depends on: I2, I3.

Includes HTTPX2 finite timeouts, model metadata, reference translation,
`image create`, wait, streaming artifact, error normalization, mocked
contracts and opt-in live smoke test.

Validation: contract suite passes; explicitly enabled live test creates
one local image; secret sentinel absent.

This increment freezes provider-native parameter syntax after real
provider experience.

### I5: First asynchronous video vertical slice

Outcome: Google or Runway, selected by current API stability at
implementation time, submits video; later process
resumes/waits/downloads.

Depends on: I4.

Validation: mocked submit → process exit → new process → wait works
against temporary SQLite; opt-in live short-video smoke test when
explicitly enabled.

### I6: Complete MVP provider set

Outcome: Google, OpenAI, Runway, fal participate in generic commands for
supported MVP media kinds.

Depends on: I4, I5.

Validation: shared contracts pass for all; at least two independently
authenticated providers pass explicitly enabled live generation smoke
tests; no adapter adds root commands.

### I7: Agent handoff and release hardening

Outcome: Claude Code uses PixGen from the Skill without
provider-specific workflow knowledge.

Depends on: I6.

Includes complete info/doctor, Cyclopts-supported completion,
uvx/tool/--with docs, JSON/exit compatibility tests, package/license,
and release-candidate QA decision.

Validation: clean install; scripted agent-like info → doctor → model
discovery → generation JSON → local artifact; full default suite passes.

## Definition of done

All acceptance criteria pass; default tests make no billable requests;
configured static analysis and package build/install checks pass; docs
match actual CLI; no unresolved blocker remains.
