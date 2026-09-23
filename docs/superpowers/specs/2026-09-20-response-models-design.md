# Pixgen Response Models Design

**Status:** Approved design

**Date:** 2026-09-20
**Scope:** Document the response-model decision only. This design does not
authorize implementation.

## Decision

Pixgen separates internal normalized provider results from its stable public
CLI JSON contract.

Provider SDK and HTTP response types are private adapter concerns. Each adapter
normalizes only the facts Pixgen needs into an internal `ProviderGeneration`:

- optional provider job ID;
- normalized lifecycle status;
- candidate media awaiting local persistence;
- optional provider usage facts; and
- provider-safe diagnostic details.

The runtime turns that internal result into persisted Pixgen facts and then
constructs public output models. Raw provider responses, credentials,
authorization headers, signed URLs, and arbitrary provider-native fields are
never persisted or emitted.

## Public model set

The planned public-contract module is `src/pixgen/core/results.py`. Rendering
remains in `src/pixgen/output.py`.

```text
GenerationResponse
├── schema_version: Literal[1]
├── id: UUIDv7
├── operation, provider, model, status
├── provider_job_id: str | null
├── artifacts: tuple[ArtifactResponse, ...]
├── usage: UsageResponse | null
├── error: ErrorDetail | null
├── created_at, completed_at
└── metadata: documented provider-neutral fields only

BatchResponse
├── schema_version: Literal[1]
├── requested, completed, failed
└── generations: ordered tuple[GenerationResponse, ...]

ErrorResponse
├── schema_version: Literal[1]
└── error: ErrorDetail
```

`ArtifactResponse` contains only the final local artifact facts: absolute path,
media kind and media type, byte size, SHA-256, and optional dimensions or
duration. It never includes a remote URL.

`UsageResponse` represents only safe, normalized usage details that Pixgen can
define consistently. It is optional because providers do not always supply
enough information for exact cost attribution.

`ErrorDetail` has stable `code`, `message`, and `retryable` fields, plus
optional `provider` and field-level errors. It is embedded in a failed batch
item; a command-level failure is emitted as `ErrorResponse` to stderr.

## Lifecycle

The normalized lifecycle vocabulary is:

```text
pending → running → completed
                  ↘ failed
                  ↘ cancelled
```

`pending` means Pixgen accepted and recorded the request but has not confirmed
provider submission. `running` means a provider job exists and can be polled or
resumed. `completed`, `failed`, and `cancelled` are terminal.

Synchronous image generation normally completes without a provider job ID;
therefore `provider_job_id` is explicitly `null`, not omitted. An asynchronous
video generation exposes the safe provider job ID when Pixgen needs it to
resume or poll the generation.

## Compatibility and serialization

All public models are frozen Pydantic models and serialize using explicit,
snake_case field names. State-bearing optional fields remain present as `null`
rather than being omitted.

`schema_version` is fixed at `1`. Version 1 may add optional fields but must
not rename, remove, or change the meaning of existing fields. A breaking change
requires a new schema version.

Public `metadata` is an explicit extension point only for documented,
provider-neutral information. It is not a passthrough container for provider
payloads.

## Rationale

The CLI JSON output is a compatibility promise to humans, shell scripts, CI,
and coding agents. Provider response formats and SDK types change independently
and are unsuitable as that promise. A small normalization layer is already
required for lifecycle translation, artifact persistence, error sanitization,
and ordered partial-batch handling, so exposing one shared model would couple
the public contract to implementation details without removing meaningful work.

## Future verification

When implementation is separately authorized, tests must cover:

- JSON-schema snapshots for every public response model;
- serialization examples for each lifecycle state;
- sanitization proving secrets, signed URLs, and raw provider payloads cannot
  enter JSON or persistence;
- ordered partial batches with completed and failed entries; and
- compatibility checks for the documented version-1 JSON examples.

## Evidence

- Pydantic documentation supports discriminated unions for typed alternatives
  and JSON Schema generation from `BaseModel`.
- Current provider research confirms that image responses may be synchronous
  while video or batch workflows use asynchronous provider job identifiers;
  Pixgen normalizes those differences rather than exposing them directly.
