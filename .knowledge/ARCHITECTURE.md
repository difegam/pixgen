# Architecture

## Overview

PixGen is a local Python CLI with no daemon or PixGen server. Cyclopts
parses commands into typed Pydantic requests. A provider registry
selects an adapter. The adapter validates model capabilities, resolves
credentials, uploads references when necessary, and calls the provider
through HTTPX2. Sanitized generation state is persisted in SQLite;
completed artifacts stream to local files.

Provider extensibility is an MVP requirement, so Python entry points +
Pluggy form a deliberately small public extension boundary.

``` mermaid
flowchart LR
  A[User/agent] --> B[Cyclopts CLI]
  B --> C[Typed request + validation]
  C --> D[Provider registry]
  D --> E[Provider adapter]
  E --> F[HTTPX2]
  F --> G[Provider API]
  C --> H[(SQLite)]
  E --> H
  E --> I[Local artifacts]
  J[Keyring/env] --> E
  K[YAML/PlatformDirs] --> B
  L[Entry-point plugins] --> D
  L --> M[Root doctor]
```

## System boundaries

### CLI

Owns parsing, human/JSON rendering, exit statuses, and operation
orchestration. Root namespace belongs to PixGen. Plugins receive only
`provider <name>` command space.

### Core models

Own provider-independent Generation, Artifact, MediaReference,
ModelSpec/capabilities, request, and stable error concepts. Core does
not model the union of all vendor parameters.

### Provider registry and adapters

Registry discovers built-ins/entry points, rejects duplicate provider
names, and resolves canonical `<provider>/<provider-model-id>`
identifiers.

An adapter owns model discovery/catalog, capabilities, credential
environment name, request translation, uploads, submit/poll/cancel,
error normalization, and safe provider metadata.

### Plugin manager

Initial public hooks:

1.  register provider;
2.  register commands below that provider;
3.  register checks consumed by root `pixgen doctor`.

Plugins cannot mutate root CLI, core DB schema/migrations, or credential
storage. Publish a plugin API version before third-party plugin
documentation.

### Configuration and credentials

Pydantic Settings loads non-secret YAML preferences. PlatformDirs owns
config/data/cache/state locations.

Effective config precedence: explicit command value → environment
override → YAML → default.

Credential precedence: PixGen keyring entry → provider environment
variable → missing-credentials error. Secrets are not Pydantic persisted
configuration.

### Storage

SQLModel maps a core-owned SQLite schema. Enable WAL, foreign keys, and
finite busy timeout. Plugins may persist only sanitized provider
metadata through core-owned JSON fields.

### HTTP

Use HTTPX2 \>=2.12,\<3 while compatible. Reuse clients within
operations, set finite connect/read/write/pool timeouts, and stream
artifact downloads.

## Data flow

### Submit/wait

Parse → resolve model/provider → validate roles/cardinality → resolve
secret → upload references if required → submit → persist Generation →
optionally poll → stream artifacts → persist Artifact → render output.

### Resume

Load Generation → select provider using persisted provider/job ID →
query/poll → update normalized state → download newly available
artifact.

### Diagnostics

`pixgen info` is passive. `pixgen doctor` orchestrates core plus
plugin/provider checks. `--provider` filters the root check set; there
is no provider-specific doctor command.

## Technology choices

-   **Python 3.12+**: modern typed baseline without requiring
    newest-only syntax.
-   **uv/uvx**: native Python tool execution/installation and `--with`
    plugin composition.
-   **Cyclopts**: typed nested CLI apps.
-   **Pydantic + Pydantic Settings**: typed external boundaries/config
    sources.
-   **YAML + PlatformDirs**: editable non-secret config and OS-correct
    paths.
-   **keyring**: native desktop secret storage; env fallback for
    headless use.
-   **HTTPX2**: maintained async/sync HTTP, uploads/polling/streaming;
    patched baseline 2.12+.
-   **SQLModel + SQLite**: local resumable jobs/history without a
    server.
-   **Pluggy + entry points**: provider extension requirement, following
    the proven `llm` pattern.

## Data model

### Generation

Fields/concepts: immutable local ID, provider, namespaced model, media
kind, normalized status, provider job ID, sanitized request/prompt,
timestamps, safe provider metadata, normalized error, optional
actor/provenance.

Normalized statuses:

``` text
submitted
processing
completed
failed
cancelled
```

### Artifact

Generation relation, media type/kind, local path, safe remote source
when appropriate, safe metadata. Never persist sensitive signed URLs.

### MediaReference

Source plus role/media type. Initial role vocabulary:

``` text
image
reference
start-frame
end-frame
video
audio
mask
```

A model declares allowed roles and cardinality. Data-model support does
not make every role an MVP CLI feature.

### ModelSpec

Namespaced ID, display name, media kind, capabilities, accepted
roles/cardinality, generic constraints, and provider-specific parameter
metadata/schema where useful. Model catalogs are provider data, not DB
migrations.

## Interfaces and integrations

MVP root shape:

``` text
pixgen image create
pixgen video create
pixgen model list|get
pixgen generation get|list|wait|cancel
pixgen provider list|get|<provider> ...
pixgen keys set|list|delete
pixgen config get|path
pixgen plugins
pixgen info
pixgen doctor
```

Global machine conventions include `--json`, `--no-color`, `--quiet`,
`--version`, and `--help`.

JSON is versioned. Successful generation output includes schema version,
local ID, provider, model, status, and artifact paths. Errors include
schema version, stable code, message, provider when relevant, and
retryability when known.

Provider-native parameters use one controlled generic escape hatch
finalized during the first provider slice. Provider-specific operations
live under `provider <name>`.

## Security and privacy

-   Resolve secrets only at execution.
-   Keep secrets out of serializable history request models.
-   Redact authorization headers/logging.
-   Sanitize provider metadata before persistence.
-   Treat signed URLs as potentially sensitive.
-   Upload local files only when the selected provider requires it.
-   `info`, `doctor`, and `keys list` expose presence/source only.
-   Plugins execute in-process and are trusted installed code; no
    sandbox is promised.

## Failure handling

Known invalid model/reference combinations fail before submission.
Provider
auth/rate-limit/invalid/unavailable/timeout/generation/cancellation
failures map to stable errors. Wait timeout leaves the job resumable.
Artifact download failure does not change provider-completed generation
to failed. DB lock waits are finite. Plugin load failures surface
through `plugins`/`doctor`.

## Deployment

``` bash
uvx pixgen --help
uv tool install pixgen
uv tool install pixgen --with pixgen-provider-example
```

No background service.

## Observability

Structured errors, optional redacted verbose logging, persistent
generation state, `info`, and centralized `doctor`. No
telemetry/metrics/tracing backend in MVP.

## Architectural decisions

### Decision: normalize capabilities, not complete provider APIs

Normalize stable concepts; preserve the rest through provider
metadata/native parameters/commands. Avoid both a weak lowest-common
denominator and an unstable universal superset.

### Decision: typed media references are first-class

Observed current models accept multiple images, start/end frames,
video/audio references, and model-specific cardinalities. Represent
those roles directly instead of multiplying request classes.

### Decision: Generation is the local job record

Do not create separate generic Job and Generation entities in MVP.

### Decision: centralized root doctor

Expose only `pixgen doctor`; providers contribute checks.

### Decision: plugins are ordinary Python packages

Use entry points + Pluggy and uv/Python installation. Do not build
package management.

### Decision: workflows remain deferred

Higgsfield validates workflows as a useful later layer, but MVP first
validates provider/media/job contracts. Add a workflow extension only
when implementing the first real P1 workflow.

## References

-   https://github.com/higgsfield-ai/skills/blob/main/higgsfield-generate/references/media-inputs.md
    --- reference-role requirements.
-   https://github.com/higgsfield-ai/skills/blob/main/higgsfield-generate/references/workflows.md
    --- workflow separation.
-   https://docs.astral.sh/uv/guides/tools/ --- tool/plugin
    installation.
-   https://github.com/pydantic/httpx2 --- HTTP client.
-   https://github.com/pydantic/httpx2/security/advisories/GHSA-8xx6-hgc6-gc2m
    --- patched baseline.
-   https://sqlmodel.tiangolo.com/release-notes/ --- persistence
    dependency.
-   https://cyclopts.readthedocs.io/en/latest/api.html --- nested
    commands.
-   https://llm.datasette.io/en/stable/plugins/plugin-hooks.html ---
    plugin pattern.
