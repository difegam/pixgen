# Pixgen 0.1 — Product, Architecture, and Implementation Plan

Verified and revised: 2026-09-18.

## 1. Product contract

Pixgen is an open-source, local, bring-your-own-key command-line tool for
generative images and video. It gives humans, shell scripts, CI jobs, and coding
agents one typed interface across independently authenticated providers.

```text
human or agent
    → stable CLI and versioned JSON
    → typed Pixgen requests
    → built-in provider adapter
    → provider API
    → explicit local artifact
```

Pixgen never requires a hosted Pixgen service, account, proxy, API key, MCP
server, or background daemon. The selected provider owns inference, billing,
moderation, quotas, and remote retention.

### Principles

1. **CLI first.** The CLI is the product contract. Python internals remain free
   to change until a real public extension API is justified.
2. **BYOK.** Credentials resolve from secure desktop storage and then the
   provider-standard environment variable. Pixgen never brokers credentials.
3. **Typed boundaries.** CLI input, configuration, provider requests, provider
   results, persistence rows, JSON output, and errors all have explicit types.
4. **Small common core.** Normalize only concepts that genuinely map across the
   shipped providers. Validate provider-native options inside the adapter.
5. **Agent-safe output.** Every command supports `--json`, stable error codes,
   documented exit statuses, and predictable absolute artifact paths.
6. **No surprise spending.** Validate locally before submission, never retry an
   ambiguous paid submission, and make independent variant requests explicit.
7. **No secret persistence.** Credentials, authorization headers, signed URLs,
   and unsanitized provider responses never enter configuration, SQLite, output,
   or logs.

## 2. Release scope

### Included in 0.1

- Google image creation, reference-guided creation, and editing.
- Google text-to-video and start-frame-to-video through Gemini Omni Flash.
- OpenAI image creation, reference-guided creation, and editing.
- Native image batches where a model supports them.
- Explicit concurrent image variants as independent paid generations.
- Curated model discovery and capability inspection.
- Local validation of operations, media roles, counts, formats, sizes, and
  provider-native parameters.
- Secure keyring credentials with provider-standard environment fallback.
- Persistent generation and artifact history in SQLite.
- Background video submission, polling, cancellation, and cross-process resume.
- Atomic local artifact writes and collision protection.
- Versioned JSON output, stable errors, and stable exit codes.
- Passive `info`, active `doctor`, and one provider-neutral Agent Skill.

### Explicitly deferred

- External provider plugins and a versioned public plugin API.
- Runway, fal, Replicate, Black Forest Labs, Stability, and other providers.
- Veo-specific controls, last-frame interpolation, video references, extension,
  editing, and audio inputs.
- Remote media URLs, project-local configuration, model refresh, aliases, and
  automatic model or cost routing.
- `storage`, `stats`, `agent`, pruning, config mutation, import/export, search,
  workflow DAGs, MCP, local inference, audio generation, and 3D.

### Non-goals

Pixgen 0.1 is not a hosted API, provider proxy, billing system, web application,
workflow engine, gallery, marketplace, cloud-storage service, or generic AI
orchestration framework.

## 3. CLI contract

### Command tree

```text
pixgen
├── image
│   ├── create
│   └── edit
├── video
│   └── create
├── generation
│   ├── get
│   ├── list
│   ├── wait
│   └── cancel
├── model
│   ├── list
│   └── get
├── keys
│   ├── set
│   ├── list
│   └── delete
├── config
│   ├── get
│   └── path
├── info
├── doctor
├── --install-completion
├── --version
└── --help
```

The root namespace contains no provider-specific commands. There is no
`provider` or `plugins` command in 0.1 because the providers are known built-ins
and model IDs already identify their provider.

### Prompts

The prompt is positional. `--prompt` is an explicit alias for generated command
lines and prompts beginning with a dash.

```bash
pixgen image create "A modern cabin beside a Norwegian fjord" \
  --model google/gemini-3.1-flash-image \
  --aspect-ratio 16:9 \
  --output cabin.png
```

The implementation must verify the exact Cyclopts declaration with a CLI test
covering both forms. The two forms are mutually exclusive when parsed together.

### Image creation and editing

The commands express distinct user intent:

- `image create` creates a new composition. Repeated `--reference` inputs guide
  subject, composition, or style.
- `image edit` transforms one or more repeated `--image` inputs. It may accept
  one `--mask` when the selected model supports masks.

```bash
# Text-to-image
pixgen image create "A ceramic teapot on a walnut table" \
  --model google/gemini-3.1-flash-image \
  --output teapot.png

# New composition from multiple references
pixgen image create \
  "Place the product from the first image in the visual style of the second" \
  --reference product.png \
  --reference style.png \
  --model google/gemini-3.1-flash-image \
  --output campaign.png

# Transform an existing image
pixgen image edit "Replace the background with a neutral studio backdrop" \
  --image product.png \
  --mask background-mask.png \
  --model openai/gpt-image-2.5-sunburst \
  --output product-studio.png
```

The adapter may map both intents to the same provider endpoint. The CLI and core
do not infer intent from provider endpoint names.

### Video creation

The 0.1 video contract is deliberately small:

```bash
# Text-to-video; waits by default
pixgen video create "A slow aerial pass over a volcanic island" \
  --model google/gemini-omni-1.1-flash \
  --output island.mp4

# Start-frame-to-video; return after submission
pixgen video create "Slow dolly toward the cabin while snow falls" \
  --start-frame cabin.png \
  --model google/gemini-omni-1.1-flash \
  --output cabin.mp4 \
  --no-wait --json
```

`--wait`, `--no-wait`, `--wait-timeout`, and `--wait-interval` apply only to
video creation and `generation wait`. Image provider endpoints are synchronous,
so exposing `--no-wait` there would promise resumability the provider cannot
supply.

### Model selection

Generation commands do not accept `--provider`.

```text
explicit --model provider/model
    ↓ otherwise
defaults.image_model or defaults.video_model
    ↓ otherwise
invalid_configuration, exit 2
```

The provider is the segment before the first `/`; everything after the first
slash is the provider-local model ID. Parsers split once from the left so future
aggregator IDs may contain additional slashes.

### Native count and independent variants

Image commands support two mutually exclusive forms:

```bash
# One provider request asking for four outputs
pixgen image create "Four logo explorations" --count 4

# Four independent paid requests with identical logical input
pixgen image create "Four logo explorations" --variants 4
```

- `--count N` is allowed only when the selected model advertises native
  multi-output support. Pixgen sends one provider request.
- `--variants N` creates N independent generations concurrently. Inputs and
  parameters remain identical; provider stochasticity produces variation.
- Pixgen never invents seeds or mutates style, quality, resolution, or other
  parameters behind the user's back.
- Variant concurrency is fixed at four in 0.1. A semaphore bounds submission.
- Each variant has its own UUIDv7, database row, status, error, and artifacts.
- Machine results remain in submission order, not completion order.

If `--output hero.png` produces N outputs, names are `hero-1.png` through
`hero-N.png`. The unsuffixed name is unused. This rule applies to either native
count or variants; combining them is invalid.

### Local media and output paths

All 0.1 media inputs are local files. `MediaReference` does not accept URLs.
Callers must download a remote asset explicitly before using it.

- Never overwrite without `--force`.
- Never create a missing parent directory without `--create-dirs`.
- Validate collisions and parent directories before provider submission.
- Resolve reported artifact paths to absolute paths.
- Write to a temporary sibling file, flush and fsync it, then atomically replace
  the destination.
- If `--output` is omitted, write under the PlatformDirs data directory's
  `artifacts/` child with a generated name.

### Human and machine output options

Every command accepts a reusable typed output-option group containing `--json`,
`--quiet`, and `--no-color`. `NO_COLOR` is equivalent to `--no-color`.

`--json` produces exactly one JSON document, disables Rich progress and
decoration, and never mixes logs into the result stream.

## 4. Core domain contracts

> Planned files: `src/pixgen/core/models.py`, `requests.py`, `results.py`,
> `validation.py`, and `errors.py`.

Core is transport-free and storage-free. Models are frozen where mutation is
not part of their lifecycle.

### Model IDs, media kinds, roles, and capabilities

```python
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


type ModelId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*/.+$"),
]


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class MediaRole(StrEnum):
    IMAGE = "image"
    REFERENCE = "reference"
    MASK = "mask"
    START_FRAME = "start-frame"


class Capability(StrEnum):
    TEXT_TO_IMAGE = "text-to-image"
    REFERENCE_TO_IMAGE = "reference-to-image"
    IMAGE_EDIT = "image-edit"
    TEXT_TO_VIDEO = "text-to-video"
    IMAGE_TO_VIDEO = "image-to-video"


class MediaReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: MediaRole
    path: Path
```

Do not include unshipped roles such as end frame, video, or audio merely to
reserve names. Adding a role before the plugin API is public is cheap.

### Media specifications

```python
class MediaRoleSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum: int = 0
    maximum: int = 1
    formats: frozenset[str]
    max_bytes: int | None = None
```

Roles absent from a model's mapping are invalid. Reference order is preserved.
Cardinality and size limits belong to the exact model manifest, not a broad
provider default.

### Discriminated requests

Use separate models instead of one request full of optional fields:

```python
from typing import Literal

from pydantic import BaseModel, Field


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class ImageCreateRequest(BaseModel):
    operation: Literal["image-create"] = "image-create"
    prompt: str
    model: ModelId
    references: tuple[MediaReference, ...] = ()
    aspect_ratio: str | None = None
    resolution: str | None = None
    count: int = 1
    params: dict[str, JsonValue] = Field(default_factory=dict)


class ImageEditRequest(BaseModel):
    operation: Literal["image-edit"] = "image-edit"
    prompt: str
    model: ModelId
    images: tuple[MediaReference, ...]
    mask: MediaReference | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    count: int = 1
    params: dict[str, JsonValue] = Field(default_factory=dict)


class VideoCreateRequest(BaseModel):
    operation: Literal["video-create"] = "video-create"
    prompt: str
    model: ModelId
    start_frame: MediaReference | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | None = None
    params: dict[str, JsonValue] = Field(default_factory=dict)


type GenerationRequest = (
    ImageCreateRequest | ImageEditRequest | VideoCreateRequest
)
```

The implementation must configure the union discriminator on `operation` when
embedding the union in another Pydantic model.

### Typed parameter metadata

`ParameterSpec` is a discriminated union rather than one object containing many
unrelated optional fields:

```python
class IntegerParameterSpec(BaseModel):
    kind: Literal["integer"] = "integer"
    minimum: int | None = None
    maximum: int | None = None
    default: int | None = None
    description: str = ""


class EnumParameterSpec(BaseModel):
    kind: Literal["enum"] = "enum"
    values: tuple[str, ...]
    default: str | None = None
    description: str = ""


type ParameterSpec = (
    StringParameterSpec
    | IntegerParameterSpec
    | NumberParameterSpec
    | BooleanParameterSpec
    | EnumParameterSpec
)
```

Basic scalar, range, and enum validation may be shared. Cross-field rules live
in provider-specific Pydantic option models and validators. There is no generic
`ParameterConstraint` language.

### Model specifications

```python
from datetime import date

from pydantic import AnyHttpUrl


class ModelSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ModelId
    display_name: str
    kind: MediaKind
    capabilities: frozenset[Capability]
    media: dict[MediaRole, MediaRoleSpec]
    parameters: dict[str, ParameterSpec]
    documentation_url: AnyHttpUrl
    verified_at: date
    supports_cancel: bool = False
```

Model manifests power `model list/get`, local validation, CLI help, the Agent
Skill, and provider contract tests. They are curated code beside each adapter;
0.1 does not scrape websites or cache dynamic catalogs.

### Validation order

All checks run before credential resolution, database insertion, or provider
submission where possible:

1. Resolve and parse the canonical model ID.
2. Confirm that the operation's capability is advertised.
3. Confirm that supplied media roles are accepted.
4. Validate role cardinality, local existence, regular-file status, extension,
   and byte size.
5. Validate normalized parameters against the model manifest.
6. Parse provider-native `params` through the adapter's typed options model.
7. Validate output collisions and parent-directory policy.

Provider-specific cross-field errors are still `invalid_request` and must name
the offending fields.

## 5. Provider boundary and implementations

> Planned files: `src/pixgen/providers/base.py`, `google.py`, and `openai.py`.

The provider contract is internal in 0.1:

```python
from collections.abc import Sequence
from typing import Protocol


class Provider(Protocol):
    name: str

    async def list_models(self) -> Sequence[ModelSpec]: ...
    async def submit(self, request: GenerationRequest) -> ProviderGeneration: ...
    async def get(self, provider_job_id: str) -> ProviderGeneration: ...
    async def cancel(self, provider_job_id: str) -> ProviderGeneration: ...
```

Both adapters accept provider-local model IDs after core splits the canonical ID
once. Adapters never parse canonical IDs themselves.

### Google

Use the official async `google-genai` SDK because it removes meaningful
complexity around the Interactions API, media payloads, background interactions,
polling, and cancellation.

0.1 Google models:

| Display name | Canonical ID | Kind |
| --- | --- | --- |
| Nano Banana 2 | `google/gemini-3.1-flash-image` | image |
| Nano Banana 2 Lite | `google/gemini-3.1-flash-lite-image` | image |
| Nano Banana Pro | `google/gemini-3-pro-image` | image |
| Gemini Omni Flash | `google/gemini-omni-1.1-flash` | video |

Google image creation and editing and Gemini Omni video use the Interactions
API. Video requests use background execution so the returned interaction ID can
be persisted, polled, cancelled, and resumed after the CLI exits.

Background execution requires `store=true`. Provider-side retention is therefore
not optional for resumable Google video. As of verification, Google documents a
one-day retention period for the free tier and up to 55 days for paid tiers,
with shorter paid-tier settings available. Surface this fact in documentation
and `model get`; do not imply that all state is local.

References:

- [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Background execution](https://ai.google.dev/gemini-api/docs/background-execution)
- [Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation)
- [Gemini Omni Flash](https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash)
- [Google model catalog](https://ai.google.dev/gemini-api/docs/models)

### OpenAI

Use direct HTTPX2 because the required surface is two small endpoints and does
not justify an additional provider SDK:

```text
POST /v1/images/generations
POST /v1/images/edits
```

0.1 OpenAI models:

| Display name | Canonical ID | Kind |
| --- | --- | --- |
| GPT-Image-2.5 Sunburst | `openai/gpt-image-2.5-sunburst` | image |
| GPT-Image-2.5 Flare | `openai/gpt-image-2.5-flare` | image |
| GPT-Image-2 | `openai/gpt-image-2` | image |

Reference-guided creation may use the edits endpoint internally. Pixgen's user
intent remains `image create`; endpoint selection is an adapter detail.

References:

- [OpenAI image generation](https://developers.openai.com/api/reference/cli/resources/images/methods/generate)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models/all)

### Deprecated and intentionally omitted APIs

- Google Imagen models shut down on 2026-08-17. Do not implement them.
- Veo 2 and 3.0 shut down on 2026-06-30. Veo 3.1 remains available but is
  deferred because Omni satisfies the reduced 0.1 video contract through the
  same API family used for Google images.
- OpenAI Sora and the Videos API are deprecated and scheduled to shut down on
  2026-09-24. Do not build a video adapter around them.
- Deprecated GPT Image 1 models are absent from the manifest.

References:

- [Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
- [OpenAI deprecated video API](https://developers.openai.com/api/reference/typescript/resources/videos/methods/create)

### Retry ownership

Paid submissions are not automatically retried after an ambiguous network
failure. A timeout after request bytes leave the process may already represent a
billable generation, and a blind retry can duplicate charges.

Safe reads such as interaction polling may use `stamina` with exponential
backoff and jitter. Respect `Retry-After`. The generation wait timeout governs
the complete poll lifecycle; retry backoff does not reset it. Translate provider
SDK and HTTPX2 failures into Pixgen errors before they cross the adapter boundary.

## 6. Configuration

> Planned files: `src/pixgen/config/models.py`, `loader.py`, and `paths.py`.

Use TOML, Pydantic Settings, and PlatformDirs. Do not search the working tree for
configuration.

```text
PlatformDirs user config/config.toml
        ↑ overridden only by
PIXGEN_CONFIG=/absolute/path/to/config.toml
```

`PIXGEN_CONFIG` must be absolute. A relative override is
`invalid_configuration` because its meaning changes with the caller's working
directory.

### Source precedence

```text
explicit initialization value → PIXGEN_* environment → config.toml → defaults
```

`.env`, project files, and Pydantic file-secret sources are not loaded.

### Example config

```toml
[defaults]
image_model = "google/gemini-3.1-flash-image"
video_model = "google/gemini-omni-1.1-flash"

[generation]
output_dir = "/Users/example/Pictures/pixgen"
wait_timeout = 600.0
wait_interval = 3.0
```

### Settings implementation

```python
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class Defaults(BaseModel):
    image_model: ModelId | None = None
    video_model: ModelId | None = None


class GenerationSettings(BaseModel):
    output_dir: Path | None = None
    wait_timeout: float = Field(default=600.0, gt=0)
    wait_interval: float = Field(default=3.0, gt=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PIXGEN_",
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
    )

    defaults: Defaults = Field(default_factory=Defaults)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del dotenv_settings, file_secret_settings
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(
                settings_cls,
                toml_file=resolve_config_path(),
            ),
        )
```

Import `BaseSettings`, `SettingsConfigDict`, and settings sources from
`pydantic_settings`, never from `pydantic`. Use `type[...]` and `tuple[...]`, not
the deprecated-style `typing.Type` and `typing.Tuple` aliases.

If `generation.output_dir` is `None`, resolve it to the PlatformDirs data
directory's `artifacts/` child at runtime. Do not evaluate `Path.cwd()` as a model
default.

## 7. Credentials

> Planned file: `src/pixgen/credentials.py`.

Credential resolution has no profiles:

```text
OS keyring → provider-standard environment variable → fail immediately
```

| Provider | Keyring account | Environment fallback |
| --- | --- | --- |
| Google | `google` | `GEMINI_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |

The keyring service name is `pixgen`.

```python
class CredentialResolver:
    def get(self, provider: str) -> SecretStr: ...
    def set(self, provider: str, value: SecretStr) -> None: ...
    def delete(self, provider: str) -> None: ...
    def source(self, provider: str) -> CredentialSource | None: ...
```

Rules:

1. Never accept a credential as a command-line flag.
2. `keys set PROVIDER` uses hidden input and writes only to the secure keyring.
3. If the keyring backend is unavailable, generation may still use the matching
   environment variable.
4. `keys set` fails clearly when secure storage is unavailable. Never install or
   select `keyrings.alt` automatically.
5. `keys list`, `info`, and `doctor` expose presence and source only.
6. Resolve credentials after local validation but before database insertion and
   network access.
7. Redact authorization headers and known secret values from every exception and
   log record.

## 8. Persistence and migrations

> Planned files: `src/pixgen/storage/database.py`, `models.py`, and
> `storage/migrations/`; development configuration at `alembic.ini`.

Use synchronous SQLAlchemy 2 typed declarative mappings and SQLite. Provider
network calls remain asynchronous. Database transactions are short and never
span an `await`.

### Typed rows

```python
from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GenerationRow(Base):
    __tablename__ = "generations"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    operation: Mapped[Operation] = mapped_column(
        Enum(
            Operation,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    status: Mapped[GenerationStatus] = mapped_column(
        Enum(
            GenerationStatus,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    provider_job_id: Mapped[str | None] = mapped_column(String)
    request: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    error: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON)


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"),
        index=True,
    )
    path: Mapped[str] = mapped_column(String)
    media_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
```

The implementation should add explicit nullability, indexes, uniqueness, and
relationships in the final mappings. `provider_job_id` is unique within a
provider when non-null.

### Alembic from the first release

```text
src/pixgen/storage/
├── database.py
├── models.py
└── migrations/
    ├── env.py
    ├── script.py.mako
    └── versions/
        └── 0001_initial.py
alembic.ini
```

Migrations ship inside the installed package. `database.py` constructs an
Alembic `Config` programmatically and points `script_location` at the packaged
migration directory. Commands that require storage upgrade to `head` before
opening a normal session. Passive commands such as `info` inspect paths and the
current revision without creating or migrating a database. `doctor` compares an
existing database revision to the packaged head without silently changing it.

`Base.metadata.create_all()` is allowed only in isolated tests that explicitly
need it; it is not the production migration mechanism.

### SQLite engine policy

Every connection enables:

```text
PRAGMA foreign_keys = ON
PRAGMA journal_mode = WAL
PRAGMA busy_timeout = 5000
```

Use short-lived `Session` scopes. Do not create repository, DAO, unit-of-work,
or generic service layers around SQLAlchemy in 0.1.

### Generation lifecycle

```text
validate request and output paths
        ↓
resolve credential
        ↓
insert UUIDv7 generation as pending
        ↓
submit provider request
        ↓
persist provider job ID immediately, status running
        ↓
return for --no-wait OR poll for completion
        ↓
atomically write local artifacts
        ↓
record artifact metadata, status completed
```

Normalized statuses:

```text
pending · running · completed · failed · cancelled
```

A submission failure updates the existing row to `failed`. Video provider job
IDs are persisted before returning to the caller. A later process loads the row,
selects the provider, polls the stored interaction ID, and completes artifact
handling.

Persist sanitized prompts, parameters, local paths, statuses, timestamps, safe
errors, and local artifact facts. Never persist credentials, headers, signed
URLs, complete provider responses, or binary media.

## 9. Machine contract

> Planned file: `src/pixgen/output.py`.

Every JSON response is a Pydantic model with:

```python
schema_version: Literal[1] = 1
```

### Generation success

```json
{
  "schema_version": 1,
  "id": "01995f4f-b0d2-7a31-8e6b-0f9f536124cc",
  "operation": "image-create",
  "provider": "google",
  "model": "google/gemini-3.1-flash-image",
  "status": "completed",
  "provider_job_id": null,
  "artifacts": [
    {
      "path": "/project/cabin.png",
      "media_type": "image/png",
      "size_bytes": 1842231,
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

### Variants result

```json
{
  "schema_version": 1,
  "requested": 4,
  "completed": 3,
  "failed": 1,
  "generations": [
    {"id": "...", "status": "completed", "artifacts": []},
    {"id": "...", "status": "failed", "error": {"code": "generation_failed"}}
  ]
}
```

Partial failure preserves all successful results and exits nonzero.

### Error envelope

```json
{
  "schema_version": 1,
  "error": {
    "code": "invalid_request",
    "message": "The selected model does not accept mask inputs.",
    "retryable": false,
    "provider": "openai",
    "fields": {"mask": "unsupported"}
  }
}
```

Stable error codes:

```text
invalid_request
invalid_configuration
credential_unavailable
authentication_failed
rate_limited
model_not_found
provider_unavailable
generation_failed
generation_cancelled
timeout
artifact_error
storage_error
internal_error
```

### Streams and exit codes

- Successful JSON goes to stdout.
- Error JSON goes to stderr.
- Human progress goes to stderr.
- Raw provider bodies and exception representations never pass through
  unsanitized.

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | unexpected internal error |
| 2 | usage, validation, or configuration error |
| 3 | credential or authentication error |
| 4 | provider, network, or rate-limit error |
| 5 | timeout |
| 6 | generation failure, cancellation, or partial variants |
| 7 | local storage or artifact failure |

Cyclopts parse failures use exit code 2.

## 10. Runtime and package layout

Use Python 3.14 or newer. This provides standard-library `uuid.uuid7()` and is
the single documented baseline across the project.

```text
src/pixgen/
├── __init__.py
├── __main__.py
├── runtime.py
├── cli/
│   ├── app.py
│   ├── image.py
│   ├── video.py
│   ├── generation.py
│   ├── model.py
│   └── system.py
├── core/
│   ├── models.py
│   ├── requests.py
│   ├── results.py
│   ├── errors.py
│   └── validation.py
├── providers/
│   ├── base.py
│   ├── google.py
│   └── openai.py
├── config/
│   ├── models.py
│   ├── loader.py
│   └── paths.py
├── storage/
│   ├── database.py
│   ├── models.py
│   └── migrations/
├── credentials.py
└── output.py
```

`runtime.py` is the composition root. It creates only the dependencies required
by the selected command: resolved settings first, then credentials, storage, and
providers as needed. This keeps `--help`, `config path`, and passive `info` free
of database or network side effects. Do not hide construction in global
singletons.

Start each provider in one focused module. Split it into a package only after
real size or independent test seams justify the change.

The console entry point should become:

```toml
[project.scripts]
pixgen = "pixgen.cli.app:main"
```

`src/pixgen/__main__.py` delegates to that `main()` so `python -m pixgen` uses
the identical path.

### Runtime dependencies

Initial compatible bounds, verified against current releases on 2026-09-18:

```toml
dependencies = [
    "alembic>=1.20.0,<2",
    "cyclopts>=4.25.2,<5",
    "google-genai>=2.24.0,<3",
    "httpx2>=2.12,<3",
    "keyring>=25.7",
    "platformdirs>=4",
    "pydantic>=2.13",
    "pydantic-settings>=2.15",
    "rich>=15",
    "sqlalchemy>=2.0.54,<2.1",
    "stamina>=26",
]
```

Remove SQLModel and the `pydantic-settings[yaml]` extra. Do not add an OpenAI
SDK, async SQLite driver, Pluggy, or HTTP mocking library in 0.1.

## 11. Diagnostics

`pixgen info` is passive: version, Python version, resolved paths, database
revision, keyring backend name, credential environment-variable presence,
configured defaults, and built-in providers. It performs no provider network
calls and no writes other than unavoidable initialization already completed by
the process.

`pixgen doctor` is active and produces one aggregated report:

```text
configuration  parse · unknown keys · resolved defaults
paths          config · database · artifacts · permissions
database       open · Alembic revision · WAL · foreign keys
credentials    keyring backend · Google presence · OpenAI presence
providers      Google authentication · OpenAI authentication · manifests
runtime        Python · dependency versions
```

`doctor --json` is a stable response model. Checks have stable IDs and one of
`ok`, `warning`, `failed`, or `skipped`. Diagnostic output exposes presence and
source, never secret values.

## 12. Agent integration

Ship one provider-neutral skill without an installer command:

```text
skills/pixgen/
├── SKILL.md
└── references/
    ├── image.md
    ├── video.md
    └── troubleshooting.md
```

The skill teaches agents to:

- Run `model list/get --json` instead of guessing model behavior.
- Use explicit project-local output paths.
- Distinguish `create --reference` from `edit --image`.
- Use `--no-wait`, retain the UUID, and resume video jobs.
- Interpret stable error codes rather than human strings.
- Inspect produced artifacts before modifying downstream files.
- Run `doctor --json` for setup failures.

Provider HTTP request formats, model limits, and credentials do not belong in
the skill. The CLI and `ModelSpec` are the source of that information.

## 13. Testing and verification

```text
tests/
├── unit/
│   ├── core/
│   ├── config/
│   ├── credentials/
│   ├── output/
│   └── storage/
├── providers/
│   ├── test_google.py
│   ├── test_openai.py
│   └── contract.py
├── cli/
│   ├── test_image.py
│   ├── test_video.py
│   ├── test_generation.py
│   └── test_machine_output.py
├── integration/
│   ├── test_resume_across_processes.py
│   ├── test_migrations.py
│   └── test_concurrent_variants.py
└── live/
    ├── test_google_live.py
    └── test_openai_live.py
```

### `tests/unit/core/`

Pure request, capability, media-role, parameter, and error behavior with no I/O.
These tests prove the provider-independent contract and validation order.

### `tests/unit/config/`

TOML loading, PlatformDirs resolution, `PIXGEN_CONFIG`, nested environment
overrides, unknown-key rejection, and precedence. Tests use isolated temporary
directories and never read a developer's real configuration.

### `tests/unit/credentials/`

Keyring-first resolution, provider environment fallback, unavailable-backend
behavior, hidden-input commands, and redaction. Fake backends prevent access to
the developer's real keychain.

### `tests/unit/output/`

Pydantic JSON schemas, stdout/stderr separation, Rich suppression under
`--json`, exit-code mapping, and secret-safe error rendering.

### `tests/unit/storage/`

Typed SQLAlchemy mappings, transactions, status transitions, sanitization,
artifact relations, pragmas, and Alembic revision checks against temporary
SQLite databases.

### `tests/providers/`

Adapter request translation, normalized results, model manifests, provider error
mapping, and shared behavioral contracts. Google receives an injected fake
async SDK client; OpenAI receives HTTPX2 `MockTransport` with synthetic or
sanitized responses.

### `tests/cli/`

Command parsing, prompt forms, mutually exclusive flags, local validation,
human output, machine output, and exact exit behavior through the real Cyclopts
application.

### `tests/integration/`

Cross-boundary behavior: migrations, real SQLite transactions, concurrent
variant scheduling, atomic files, and process recovery. The resume test submits
through a fake provider, exits one CLI process, and completes from the UUID in a
second process.

### `tests/live/`

Explicitly enabled, credit-consuming smoke tests against real provider APIs.
They verify only high-value integration assumptions and never run in normal CI.

### Required checks

```bash
just lint
just type-check
just test
just check
```

Pyrefly is the sole type checker. Update the stale `type-check-ty` recipe to
`uv run pyrefly check`, and update `just run` from the nonexistent `app` command
to `uv run pixgen`.

Critical tests must prove:

- Fresh and previous-revision databases upgrade to Alembic head.
- A background Google video resumes by UUID in a fresh CLI process.
- A persisted Google interaction can be cancelled.
- Variant concurrency never exceeds four and results retain submission order.
- Partial variants preserve successful outputs and exit 6.
- Invalid media and output paths fail before provider submission.
- A credential canary never appears in SQLite, JSON, exceptions, or logs.
- Every JSON document validates against its declared response model.
- Normal tests require no API keys and consume no credits.

Live tests require both an explicit marker and the matching credential:

```bash
pytest -m live_google
pytest -m live_openai
```

## 14. Acceptance criteria

0.1 is complete when all of the following are true:

1. Google image create, reference-guided create, and edit produce local files.
2. OpenAI image create, reference-guided create, and edit produce local files.
3. Google Omni text-to-video and start-frame-to-video produce local files.
4. A no-wait video survives process exit and resumes from its UUIDv7.
5. Native image count is capability-gated.
6. Independent variants run concurrently with a maximum of four and report
   partial success precisely.
7. Keyring and environment fallback work independently for both providers.
8. Credentials never appear in Pixgen-controlled persistence or output.
9. Output collisions, invalid media, and unsupported parameters fail before a
   billable provider call.
10. Every command has deterministic JSON and documented exit behavior.
11. The bundled Agent Skill completes image and video workflows without
    provider request formats embedded in its instructions.
12. Ruff, Pyrefly, pytest, pre-commit, and the dependency security scan pass.

The primary product criterion is:

> A human or coding agent can discover a current model, create or edit images
> through Google or OpenAI, create and resume a Google video, and consume
> explicit local artifacts using only the CLI's help and structured contracts.

## 15. Implementation order

This is sequencing, not authorization to start implementation. The detailed
task plan follows after this specification is approved.

1. Repair project metadata, entry point, development commands, dependencies,
   and configuration imports.
2. Implement core types, errors, machine response models, and pure validation.
3. Implement TOML paths/settings and keyring/environment credentials.
4. Implement typed SQLAlchemy rows, SQLite engine policy, and initial Alembic
   migration.
5. Implement CLI skeleton, model discovery, output rendering, `info`, and
   `doctor` with no provider generation yet.
6. Implement Google image vertical slice and its tests.
7. Implement Google background Omni video, persistence, resume, and cancel.
8. Implement OpenAI image vertical slice.
9. Implement native count, concurrent variants, atomic artifact handling, and
   cross-provider contract tests.
10. Write the bundled Agent Skill, run live smoke tests explicitly, and complete
    release verification.

## 16. Decisions and removals

| Area | 0.1 decision |
| --- | --- |
| Python | 3.14+ everywhere |
| Configuration | user-level TOML plus absolute `PIXGEN_CONFIG` override |
| Credentials | keyring, then `GEMINI_API_KEY` or `OPENAI_API_KEY`; no profiles |
| Storage | synchronous typed SQLAlchemy 2 + SQLite + Alembic |
| Public IDs | standard UUIDv7 |
| Providers | built-in Google and OpenAI only |
| Google transport | official async `google-genai` SDK |
| OpenAI transport | direct HTTPX2 |
| Video | Gemini Omni Flash; text or one start frame |
| Plugins | deferred; internal provider protocol only |
| Media sources | local paths only |
| Image batching | capability-gated native `--count` |
| Image variants | explicit `--variants`; identical requests; concurrency four |
| Cross-parameter rules | adapter Pydantic validators, no constraint DSL |
| Type checking | Pyrefly only |
| Agent support | one bundled provider-neutral skill; no installer command |

Removed dependencies or concepts: SQLModel, YAML, Pluggy, provider profiles,
custom Base32 IDs, ambiguous ID prefixes, provider commands, dynamic model
catalogs, remote media URLs, and speculative provider subpackages.

## 17. Risks and stop conditions

### Provider drift

Model IDs, limits, and API shapes change quickly. Each manifest records a source
URL and verification date. Provider contract and opt-in live tests must be easy
to run. Do not duplicate exact limits across narrative documents.

### Background retention

Google background interactions are stored remotely. Pixgen must state this
clearly. If the provider removes or materially changes resumable background
execution, reassess the local video contract before adding workarounds.

### Normalization pressure

If a provider feature does not fit the common request without conditionals that
affect other providers, leave it in typed provider parameters or defer it. Do
not turn the core into the union of every vendor API.

### External plugin timing

Do not publish a plugin API until Google and OpenAI adapters prove the internal
provider contract. When external plugins become a real milestone, design and
version a smaller public surface separately.

### Product stop condition

If users converge on one provider or aggregator and direct-provider switching
has little practical value, stop expanding adapters and simplify around actual
usage rather than preserving the original multi-provider ambition.
