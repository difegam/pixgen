# Architecture

## Overview

Pixgen 0.1 is a local Python 3.14 CLI. Cyclopts parses commands into frozen
Pydantic requests. An internal registry selects Google or OpenAI from the
canonical model ID. A pure function validates the request against that model's
manifest. The adapter validates provider-native options, calls the provider,
and returns a normalized result. SQLAlchemy rows persist generation state in
SQLite; Alembic manages schema; artifacts are regular local files.

The functional core lives in `core/`, which holds pure types and validation.
`application.py` owns I/O, ordering, and failure handling. `Provider` is the
only protocol, because it's the only boundary with more than one
implementation.

`pixgen.md` holds the full contracts; this document holds the boundaries and
the flows between them.

```mermaid
flowchart LR
  A[Human or agent] --> B[Cyclopts CLI]
  B --> C[Pydantic request]
  C --> D[Core validation]
  D --> E[Runtime composition]
  E --> F[Google adapter]
  E --> G[OpenAI adapter]
  F --> H[google-genai async SDK]
  G --> I[HTTPX2]
  H --> J[Google Interactions API]
  I --> K[OpenAI Images API]
  E --> L[(SQLAlchemy + SQLite)]
  L --> M[Alembic]
  E --> N[Atomic local artifacts]
  O[Keyring or provider env] --> E
  P[TOML + PlatformDirs] --> E
```

## Boundaries

### CLI

`src/pixgen/cli/` owns parsing, help, human rendering, JSON selection, and exit
status. It does not construct provider payloads or issue SQL.

### Core

`src/pixgen/core/` owns provider-independent request/result types, media roles,
capabilities, stable errors, and pure validation. It imports neither transport
nor SQLAlchemy, and no adapter.

Validation splits one way: Pydantic checks field types, the `ModelId` pattern,
and non-empty prompts. `core/validation.py` checks everything that depends on
the selected model. `validate_request(request, spec)` collects `FieldError`
entries rather than raising, so one call reports all problems at once. The
resulting list becomes the `fields` map of an `invalid_request` error
directly.

`MediaRoleSpec.formats` on the resolved manifest is the only authority on
accepted formats. There is no global extension constant, because the answer
differs per provider.

### Application

`src/pixgen/application.py` owns the generation use cases. It coordinates
validation, credential resolution, short persistence operations, provider
invocation, artifact writing, and public-result assembly. It does not parse
commands, render output, or touch concrete SDK types.

`video create --no-wait` and `generation wait` must complete the same
generation from two different entry points. Everything else is orchestration
the CLI shouldn't handle. It's a single module, not a package, because 0.1
has three use cases plus resume.

### Providers

`src/pixgen/providers/base.py` defines an internal async protocol. The built-in
Google and OpenAI modules own exact model manifests, provider-native typed
options, request translation, response translation, and error mapping.

The internal protocol is not a 0.1 public plugin API.

### Runtime

`src/pixgen/runtime.py` is the explicit composition root. It lazily creates only
the settings, credentials, storage, and providers required by the selected
command. Passive commands therefore avoid database and network side effects.
Dependencies are injected; provider clients and database sessions are not
global singletons.

### Configuration and credentials

Pydantic Settings loads only the PlatformDirs user `config.toml`, or an absolute
`PIXGEN_CONFIG` override. Nested `PIXGEN_*` variables override TOML. There is no
project config or `.env` discovery.

Credentials resolve from OS keyring and then `GEMINI_API_KEY` or
`OPENAI_API_KEY`. Secrets never become settings fields or persisted request
data.

### Storage

SQLAlchemy 2 typed rows map generations and artifacts. SQLite uses WAL, foreign
keys, and a finite busy timeout. Alembic migrations ship with the package.
Storage-using commands upgrade to head before normal sessions; passive
diagnostics only check the current revision.

`storage/generations.py` has module-level typed functions that take an
explicit `Session`. There's no repository class, DAO, or unit-of-work. Passing
the session explicitly makes the transaction rule auditable: a reader can see a
session open and close in one synchronous call.

Database transactions are short, synchronous, and never span an async provider
call.

### Diagnostics

`src/pixgen/diagnostics.py` owns `DoctorContext` and the check registry.
`cli/system.py` is a thin wrapper that renders results and maps them to exit
status, so check policy is testable without a terminal.

`info` is passive: it resolves settings and paths and reports them, touching no
credential, no database, and no network. `doctor` is the one command permitted
to open the database read-only and call providers without generating anything.

Neither mutates. `doctor` is explicitly exempt from the Storage rule that
commands upgrade to Alembic head before opening a session. It reports revision
drift and names the remedy rather than repairing it, because a diagnostic that
silently changes what it is diagnosing cannot be trusted to describe it.

A check is one async function returning a `CheckResult`. A failed prerequisite
marks its dependents `skipped` rather than `failed`, so one root cause produces
one failure.

## Concurrency

Providers are async; Cyclopts and SQLAlchemy are sync. One rule reconciles
them: **each CLI command calls `asyncio.run()` exactly once.**

`cli/*` is sync, `application.py` is async, `providers/*` is async at the
network boundary, and `storage/*` is sync and called directly from async code.
Local SQLite writes are sub-millisecond, so an executor adds nothing.

`--variants` bounds submission with `asyncio.Semaphore(4)` and reassembles
results by index, so machine output preserves submission order. Polling retries;
submissions never do.

## Core data flow

### Image

```text
parse
→ resolve model
→ validate media/parameters/output
→ resolve credential
→ insert pending UUIDv7 generation
→ submit synchronous provider image request
→ write artifacts atomically
→ persist artifacts and completed status
→ render response
```

`--count` requests a native provider batch only when advertised. `--variants`
creates independent generation records and submits identical requests under an
async semaphore of four.

### Background video

```text
parse and validate
→ resolve Google credential
→ insert pending UUIDv7 generation
→ create background Gemini interaction
→ persist interaction ID and running status
→ return for --no-wait OR poll
→ retrieve output
→ write artifact atomically
→ persist completed status
```

A later process resumes using the local UUIDv7, which resolves the provider and
stored interaction ID. Google background interactions require provider-side
storage; Pixgen documents that retention explicitly.

### Cancellation

Load the generation, reject terminal states, call the provider's remote cancel
operation, and update local state only after the provider confirms cancellation.
Pixgen never marks a remotely running job cancelled only locally.

## Data models

### Core request models

- `ImageCreateRequest`: prompt, canonical model, repeated references,
  normalized image parameters, native parameters, and native count.
- `ImageEditRequest`: prompt, repeated images, optional mask, normalized image
  parameters, native parameters, and native count.
- `VideoCreateRequest`: prompt, canonical model, optional start frame,
  normalized video parameters, and native parameters.

They form a discriminated union on `operation`.

### Persistence rows

`GenerationRow` stores UUIDv7, timestamps, provider/model/operation, normalized
status, provider job ID, sanitized request JSON, and safe error JSON.

`ArtifactRow` stores a local generation relation, absolute local path, MIME
type, byte length, and SHA-256. It does not store remote provider URLs.

## Failure policy

- Invalid capabilities, media, parameters, and paths fail before submission.
- Paid submissions are not retried after an ambiguous transport failure.
- Safe polling reads may use bounded retry with jitter and `Retry-After`.
- Provider errors are translated before leaving the adapter.
- JSON errors are stable Pydantic models; human strings are not machine state.
- A failed variant does not discard successful variants.
- Raw provider responses, credentials, headers, and signed URLs are sanitized
  before logging or persistence.
- `SIGINT` never cancels an in-flight paid submission: Pixgen persists what it
  knows, prints the UUID, and exits 6.
- `doctor` reports; it never repairs. A correct fresh install yields no
  failures.
- `ProviderGeneration` is the only inbound adapter type. A provider URL may
  exist only on `ProviderMedia.fetch_url`, in memory, between retrieval and
  atomic local write.

## Package layout

```text
src/pixgen/
├── __init__.py
├── __main__.py
├── runtime.py
├── application.py
├── cli/{app,image,video,generation,model,system}.py
├── core/{models,requests,results,errors,validation}.py
├── providers/{base,google,openai}.py
├── config/{models,loader,paths}.py
├── storage/{database,models,generations,artifacts}.py
├── storage/migrations/
├── credentials.py
└── output.py
```

Do not add repositories, DAOs, unit-of-work objects, generic services,
controllers, factories, plugin loaders, or provider subpackages without a
concrete pressure demonstrated by implementation.

## Verification boundaries

- Pure unit tests cover core types and validation.
- Provider contract tests use an injected fake Google SDK client and HTTPX2
  `MockTransport` for OpenAI.
- Integration tests use temporary SQLite databases, real Alembic upgrades,
  subprocess resume, bounded variants, and atomic files.
- Live provider tests are explicitly marked and never run in ordinary CI.
- Pyrefly is the sole type checker.

The checkout has not caught up to this layout. `pixgen.md` section 10 carries
the current-versus-target divergence table; section 15 sequences the repair.

See [`pixgen.md`](pixgen.md) for the complete contracts, file examples, test
group descriptions, and acceptance criteria.
