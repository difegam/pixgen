# Pixgen 0.1: Product, Architecture, and Implementation Plan

Verified and revised: 2026-09-20.

## 1. Product contract

Pixgen is an open-source, local, bring-your-own-key CLI for generative images
and video. Humans, shell scripts, CI jobs, and coding agents get one typed
interface across independently authenticated providers.

```text
human or agent
    → stable CLI and versioned JSON
    → typed Pixgen requests
    → built-in provider adapter
    → provider API
    → explicit local artifact
```

Pixgen doesn't need a hosted service, account, proxy, API key, MCP server, or
daemon. The provider owns inference, billing, moderation, quotas, and remote
retention.

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

### Design discipline

Pixgen borrows four ideas and avoids the rest.

1. **Functional core, imperative shell.** `core/` is pure: types and
   `validate_request`. I/O, ordering, and failure handling live in
   `application.py`. Test the parts that need no fixtures.
2. **One protocol.** `Provider` is the only protocol because it's the only
   boundary with two implementations and a likely third. Storage, config, and
   output are plain modules. One-implementation protocols are guesses dressed
   as design.
3. **Composition root.** `runtime.py` builds exactly what the command needs,
   nothing more. No global singletons, no import-time construction.
4. **Parse, don't validate.** A `GenerationRequest` is frozen and validated.
   Downstream code doesn't re-check whether the prompt is empty or model ID is
   well-formed.

Pixgen doesn't have repositories, DAOs, unit-of-work objects, factories,
generic services, controllers, dependency-injection containers, event buses, or
plugin loaders. A new module needs pressure: a second implementation, a missing
test seam, or a file that's grown too long. "It's the standard pattern" isn't
pressure. Every layer is something someone has to read.

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
- Passive `info`, active `doctor`, and one provider-neutral Agent Skill.****

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

> **Note:** Model IDs used in examples (e.g., `google/gemini-3.1-flash-image`, `openai/gpt-image-2.5-sunburst`) are defined in **§5's provider tables**. See that section for the complete 0.1 model manifest.

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
- Never create a missing parent directory without `--mkdir`.
- Validate collisions and parent directories before provider submission.
- Resolve reported artifact paths to absolute paths.
- Write to a temporary sibling file, flush and fsync it, then atomically replace
  the destination.
- If `--output` is omitted, write under the PlatformDirs data directory's
  `artifacts/` child using the generated name
  `{utc_date}-{operation}-{uuid7_suffix8}.{extension}`, for example
  `2026-09-20-image-create-536124cc.png`. The UUIDv7 suffix makes the name
  collision-free by construction, so `--force` is never required for a
  generated path.

### Human and machine output options

Every command accepts a reusable typed output-option group containing `--json`,
`--quiet`, and `--no-color`. `NO_COLOR` is equivalent to `--no-color`.

`--json` produces exactly one JSON document, disables Rich progress and
decoration, and never mixes logs into the result stream.

### Logging and verbosity

Logging uses the standard library, writes only to stderr, and defaults to
`WARNING`. The output-option group therefore also carries `--verbose`:

```text
(default)  WARNING
-v         INFO
-vv        DEBUG
```

A `RedactingFilter` installed on the Pixgen logger scrubs known credential
values and `authorization` headers from every record before formatting. Under
`--json` the logger is silenced entirely so the result stream stays a single
document. Logging is a diagnostic channel, never machine state: agents read
JSON, not log lines.

### Interrupt policy

`SIGINT` never cancels an in-flight paid submission. Once request bytes leave
the process the generation may already be billable, so Pixgen finishes
persisting what it knows, prints the generation UUID, and exits 6. The user can
resume or inspect that UUID later. A second `SIGINT` exits immediately without
further persistence.

During local validation, before any provider call, `SIGINT` exits 2 with no
database row created.

### History commands

```bash
pixgen generation get UUID [--json]
pixgen generation list [--status STATUS] [--limit N] [--since WHEN] [--json]
pixgen generation wait UUID [--wait-timeout S] [--wait-interval S] [--json]
pixgen generation cancel UUID [--json]
```

- `get` renders one `GenerationResponse` from local history. It performs no
  provider call, so a `running` row is reported as last recorded.
- `list` returns newest first. `--limit` defaults to 20; `--status` accepts one
  normalized lifecycle value; `--since` accepts an RFC 3339 timestamp or a
  duration such as `24h`. Output is a `GenerationListResponse` whose
  `generations` field holds ordered `GenerationResponse` entries.
- `wait` polls the provider until the generation reaches a terminal state or
  the timeout expires, then performs artifact handling exactly as the original
  command would have. Waiting on an already-terminal generation returns
  immediately and exits 0.
- `cancel` rejects terminal states with `invalid_request`, calls the provider's
  remote cancel operation, and updates local state only after the provider
  confirms. Cancelling a synchronous image generation is `invalid_request`
  because no resumable job exists.

`wait` and `cancel` require a row with a `provider_job_id`. Unknown UUIDs are
`invalid_request`, not `internal_error`.

### Discovery commands

```bash
pixgen model list [--provider NAME] [--kind image|video]
                  [--capability CAPABILITY] [--json]
pixgen model get MODEL_ID [--json]
```

`model list` filters the curated manifests and never performs a network call or
resolves a credential. `model get` renders one `ModelSpec`: capabilities,
accepted media roles with their cardinality and formats, typed parameters,
documentation URL, verification date, and any provider-side retention note.
Agents are expected to call these instead of guessing model behavior.

### Configuration commands

```bash
pixgen config get [KEY] [--json]
pixgen config path [--json]
```

`config get` with no argument dumps the fully resolved settings; with a dotted
key such as `generation.wait_timeout` it prints that single resolved value. An
unknown key is `invalid_configuration`. Both forms report resolved values, not
raw file contents, so precedence is visible. Neither command mutates
configuration; 0.1 has no `config set`.

`config path` prints the resolved `config.toml` path and whether it exists.

## 4. Core domain contracts

> Planned files: `src/pixgen/core/models.py`, `requests.py`, `results.py`,
> `validation.py`, and `errors.py`.

Core is transport-free and storage-free. Models are frozen where mutation is
not part of their lifecycle.

### Model IDs, media kinds, roles, and capabilities

```python
# File: src/pixgen/core/models.py

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


class Operation(StrEnum):
    IMAGE_CREATE = "image-create"
    IMAGE_EDIT = "image-edit"
    VIDEO_CREATE = "video-create"


class GenerationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: MediaRole
    path: Path
```

`MediaReference` carries no file validators. Whether a path exists, is a regular
file, has an accepted extension, and decodes as valid media are all
model-dependent questions answered by the validation pipeline below, which has
access to the `ModelSpec`. Pydantic answers only what needs no outside
knowledge.

Do not include unshipped roles such as end frame, video, or audio merely to
reserve names. Adding a role before the plugin API is public is cheap.

### Media specifications

Media specifications define the expected roles, formats, and size limits for each media type associated with a model.

```python
# File: src/pixgen/core/models.py

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
# File: src/pixgen/core/requests.py

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class RequestBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt: str = Field(min_length=1)
    model: ModelId
    params: dict[str, JsonValue] = Field(default_factory=dict)


class ImageRequestBase(RequestBase):
    aspect_ratio: str | None = None
    resolution: str | None = None
    count: int = Field(default=1, ge=1)


class ImageCreateRequest(ImageRequestBase):
    operation: Literal[Operation.IMAGE_CREATE] = Operation.IMAGE_CREATE
    references: tuple[MediaReference, ...] = ()


class ImageEditRequest(ImageRequestBase):
    operation: Literal[Operation.IMAGE_EDIT] = Operation.IMAGE_EDIT
    images: tuple[MediaReference, ...]
    mask: MediaReference | None = None


class VideoCreateRequest(RequestBase):
    operation: Literal[Operation.VIDEO_CREATE] = Operation.VIDEO_CREATE
    start_frame: MediaReference | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | None = None


type GenerationRequest = Annotated[
    ImageCreateRequest | ImageEditRequest | VideoCreateRequest,
    Field(discriminator="operation"),
]
```

Three rules this code encodes, each of which the current checkout violates:

1. **The discriminator must be `Literal`.** A bare `operation: Operation =
   Operation.IMAGE_CREATE` annotation is not a discriminator; Pydantic cannot
   tell the members apart and the union silently resolves by trial order.
   `Literal[Operation.IMAGE_CREATE]` is what makes the tag work.
2. **`params` values are `JsonValue`, not `Json`.** Pydantic's `Json` type
   parses a JSON *string* into a value. Provider-native parameters arrive as
   already-decoded values, so `dict[str, Json]` is wrong and would reject every
   real input.
3. **Video does not inherit image fields.** `count` is an image concept gated
   on native multi-output support. The two-level base keeps it off
   `VideoCreateRequest` instead of carrying a field that can never be honored.

Requests are frozen. A request is a parsed, validated value, not a mutable
builder.

### Code Example

```python
# src/pixgen/core/requests.py: constructing and validating a request

request = ImageCreateRequest(
    prompt="A cabin by a fjord",
    model="google/gemini-3.1-flash-image",
    references=(MediaReference(role=MediaRole.REFERENCE, path=Path("style.png")),),
)

# Validation happens in the application layer after the request is constructed
errors = validate_request(request, spec)
if errors:
    raise ValueError(f"Validation errors: {errors}")
```

### Typed parameter metadata

`ParameterSpec` is a discriminated union, not one object with many optional
fields:

```python
# File: src/pixgen/core/models.py

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


class StringParameterSpec(BaseModel):
    kind: Literal["string"] = "string"
    pattern: str | None = None
    default: str | None = None
    description: str = ""


class NumberParameterSpec(BaseModel):
    kind: Literal["number"] = "number"
    minimum: float | None = None
    maximum: float | None = None
    default: float | None = None
    description: str = ""


class BooleanParameterSpec(BaseModel):
    kind: Literal["boolean"] = "boolean"
    default: bool | None = None
    description: str = ""


type ParameterSpec = Annotated[
    StringParameterSpec
    | IntegerParameterSpec
    | NumberParameterSpec
    | BooleanParameterSpec
    | EnumParameterSpec,
    Field(discriminator="kind"),
]
```

`StringParameterSpec` carries an optional `pattern` because at least one real
parameter needs it: OpenAI's GPT-Image-2 and 2.5 models accept arbitrary
`WIDTHxHEIGHT` resolution strings rather than a fixed set, so `resolution`
cannot be expressed as an enum for those models.

Basic scalar, range, and enum validation may be shared. Cross-field rules live
in provider-specific Pydantic option models and validators. There is no generic
`ParameterConstraint` language.

### Model specifications

```python
# File: src/pixgen/core/models.py

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

### Code Examples

OpenAI GPT-Image-2.5 demonstrates provider-specific parameter quirks: `resolution`
accepts arbitrary `WIDTHxHEIGHT` strings (not a fixed enum), and `quality` includes
`xhigh`/`max` (only on the 2.5 models).

```python
# File: src/pixgen/providers/openai.py (model manifest excerpt)

from datetime import date
from pydantic import AnyHttpUrl

ModelSpec(
    id="openai/gpt-image-2.5-sunburst",
    display_name="GPT-Image-2.5 Sunburst",
    kind=MediaKind.IMAGE,
    capabilities=frozenset([
        Capability.TEXT_TO_IMAGE,
        Capability.REFERENCE_TO_IMAGE,
        Capability.IMAGE_EDIT,
    ]),
    media={
        MediaRole.IMAGE: MediaRoleSpec(
            minimum=1,
            maximum=10,
            formats=frozenset(["image/jpeg", "image/png", "image/webp", "image/gif"]),
            max_bytes=20 * 1024 * 1024,  # 20 MB
        ),
        MediaRole.MASK: MediaRoleSpec(
            minimum=0,
            maximum=1,
            formats=frozenset(["image/jpeg", "image/png"]),
            max_bytes=20 * 1024 * 1024,
        ),
    },
    parameters={
        "resolution": StringParameterSpec(
            kind="string",
            pattern=r"^\d{3,4}x\d{3,4}$",  # WIDTHxHEIGHT, e.g. 1024x1024
            description="Output image resolution as WIDTHxHEIGHT",
        ),
        "quality": EnumParameterSpec(
            kind="enum",
            values=("standard", "hd", "xhigh", "max"),
            default="standard",
            description="Output quality tier",
        ),
    },
    documentation_url=AnyHttpUrl("https://platform.openai.com/docs/guides/images/generations"),
    verified_at=date(2026, 9, 20),
    supports_cancel=False,
)
```

Google Gemini 3.1 Flash demonstrates a simpler case: `aspect_ratio` as a fixed
`EnumParameterSpec`, no pattern-based strings or provider-specific quirks.

```python
# File: src/pixgen/providers/google.py (model manifest excerpt)

ModelSpec(
    id="google/gemini-3.1-flash-image",
    display_name="Nano Banana 2",
    kind=MediaKind.IMAGE,
    capabilities=frozenset([
        Capability.TEXT_TO_IMAGE,
        Capability.REFERENCE_TO_IMAGE,
        Capability.IMAGE_EDIT,
    ]),
    media={
        MediaRole.REFERENCE: MediaRoleSpec(
            minimum=0,
            maximum=10,
            formats=frozenset(["image/jpeg", "image/png", "image/webp"]),
            max_bytes=20 * 1024 * 1024,
        ),
        MediaRole.MASK: MediaRoleSpec(
            minimum=0,
            maximum=1,
            formats=frozenset(["image/jpeg", "image/png", "image/webp"]),
            max_bytes=20 * 1024 * 1024,
        ),
    },
    parameters={
        "aspect_ratio": EnumParameterSpec(
            kind="enum",
            values=("1:1", "4:3", "16:9", "9:16", "3:4"),
            default="1:1",
            description="Output aspect ratio",
        ),
    },
    documentation_url=AnyHttpUrl("https://ai.google.dev/gemini-api/docs/image-generation"),
    verified_at=date(2026, 9, 20),
    supports_cancel=False,
)
```

Model manifests power `model list/get`, local validation, CLI help, the Agent
Skill, and provider contract tests. They are curated code beside each adapter;
0.1 does not scrape websites or cache dynamic catalogs.

### Validation

Validation splits one way: **Pydantic checks what needs no outside knowledge.
One pure function checks everything that depends on the selected model.**

Pydantic owns field types, the `ModelId` pattern, non-empty prompts, and
`count >= 1`. Everything else needs the `ModelSpec`, so it lives in
`core/validation.py`:

```python
# File: src/pixgen/core/validation.py

class FieldError(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    reason: str


def validate_request(
    request: GenerationRequest,
    spec: ModelSpec,
) -> list[FieldError]: ...
```

The function **collects errors instead of raising**, so a caller with a bad
mask, oversized reference, and unsupported aspect ratio gets all three at once,
not one per round-trip. A non-empty result becomes an `invalid_request` error
whose `fields` map comes straight from the list. There's no `ValidationError`
translation layer.

All checks run before credential resolution, database insertion, or provider
submission, in this order:

1. Resolve and parse the canonical model ID. *(caller: resolves the `ModelSpec`
   passed in; an unknown ID is `model_not_found`, not a field error.)*
2. Confirm that the operation's capability is advertised.
3. Confirm that supplied media roles are accepted by this model.
4. Validate role cardinality, local existence, regular-file status, format, and
   byte size.
5. Validate normalized parameters against the model manifest.
6. Parse provider-native `params` through the adapter's typed options model.
7. Validate output collisions and parent-directory policy.

Step 4 has one source of truth: **`MediaRoleSpec.formats` on the resolved model
manifest.** There is no global `SUPPORTED_IMAGE_EXTENSIONS` constant, because
the answer is genuinely model-dependent. OpenAI accepts non-animated GIF as an
image input and Google does not. A module-level set would be wrong for at least
one shipped provider on the day it was written. Format is checked by decoded
content, not by extension alone; Pillow's `verify()` provides the integrity
check, called from the pipeline rather than from a model validator.

Step 6 is the only step that calls adapter code. The adapter returns its own
`FieldError` list, which merges with the others, so provider-specific
cross-field errors stay `invalid_request` and still name the fields.

`validate_request` is the functional core. It's pure except for reading local
files, takes no clients, opens no sockets, and is where unit tests prove the
0.1 validation contract.

### Code Example

```python
# src/pixgen/core/validation.py: the validation pipeline

errors = validate_request(request, spec)
if errors:
    response = ErrorResponse(
        error=ErrorDetail(
            code=ErrorCode.INVALID_REQUEST,
            message="Validation failed",
            fields={e.field: e.reason for e in errors},
        )
    )
    # Render to stderr and exit 2
```

## 5. Provider boundary and implementations

> Planned files: `src/pixgen/providers/base.py`, `google.py`, and `openai.py`.

The provider contract is internal in 0.1:

```python
# File: src/pixgen/providers/base.py

from collections.abc import Sequence
from typing import Protocol


class Provider(Protocol):
    name: str

    def list_models(self) -> Sequence[ModelSpec]: ...
    def validate_params(
        self,
        request: GenerationRequest,
        spec: ModelSpec,
    ) -> list[FieldError]: ...

    async def submit(self, request: GenerationRequest) -> ProviderGeneration: ...
    async def get(self, provider_job_id: str) -> ProviderGeneration: ...
    async def cancel(self, provider_job_id: str) -> ProviderGeneration: ...
```

`Provider` is the only port in Pixgen 0.1. Every other module boundary is a
plain import. Introducing a second protocol requires a demonstrated need for a
second implementation, not a symmetry argument.

`list_models` and `validate_params` are synchronous: manifests are curated
static data and parameter checks are pure. Making them `async` would force an
event loop onto `model list` and onto local validation, both of which must work
without one.

`validate_params` is step 6 of the validation pipeline. It is the adapter's
only inbound call before a credential exists, so it must not touch the network
or read configuration.

Both adapters accept provider-local model IDs after core splits the canonical ID
once. Adapters never parse canonical IDs themselves.

### The internal provider result

`ProviderGeneration` crosses the adapter boundary inbound. It's internal: never
serialized to the CLI, never persisted whole, and not part of any public Python
API.

```python
# File: src/pixgen/providers/base.py

class ProviderMedia(BaseModel):
    model_config = ConfigDict(frozen=True)

    media_type: str
    data: bytes | None = None
    fetch_url: AnyHttpUrl | None = None


class ProviderUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    image_count: int | None = None


class ProviderError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    retryable: bool = False


class ProviderGeneration(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: GenerationStatus
    provider_job_id: str | None = None
    media: tuple[ProviderMedia, ...] = ()
    usage: ProviderUsage | None = None
    error: ProviderError | None = None
```

### Code Example

```python
# src/pixgen/providers/google.py: adapter submit returns normalized result

async def submit(self, request: GenerationRequest) -> ProviderGeneration:
    response = await self.client.generate(...)
    return ProviderGeneration(
        status=GenerationStatus.COMPLETED,
        provider_job_id=None,
        media=(
            ProviderMedia(media_type="image/png", data=response.image_bytes),
        ),
        usage=ProviderUsage(image_count=1),
    )
```

`ProviderMedia` carries exactly one of `data` or `fetch_url`. `fetch_url` is
the only place a provider URL exists. It's in memory between retrieval and
atomic write, never logged or persisted, and never reaches `ArtifactResponse`.

`ProviderGeneration` has no raw provider payload, credentials, headers, or
provider-native fields without Pixgen meaning. An adapter that can't express
something through these fields normalizes or drops it. Widening this model is a
design decision, not a convenience.

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

Two OpenAI-specific facts shape the manifest. GPT-Image-2 and both 2.5 models
accept **arbitrary `WIDTHxHEIGHT` resolution strings** such as `1536x864`
rather than a fixed set, so their `resolution` entry is a
`StringParameterSpec` with a `WIDTHxHEIGHT` pattern, not an
`EnumParameterSpec`. The 2.5 models add `xhigh` and `max` to the `quality`
enum, which the older models do not accept; `quality` is therefore a
per-model enum, not a provider-wide one. Both are ordinary manifest entries.
Neither belongs in core.

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

Paid submissions don't retry after ambiguous network failure. A timeout after
request bytes leave may already represent a billable generation, and retrying
blindly can duplicate charges.

Safe reads like interaction polling use `stamina` with exponential backoff and
jitter. Respect `Retry-After`. The generation wait timeout governs the whole
poll cycle; retry backoff doesn't reset it. Translate provider SDK and HTTPX2
failures into Pixgen errors before they cross the boundary.

## 6. Configuration

> Planned files: `src/pixgen/config/models.py`, `loader.py`, and `paths.py`.

Use TOML, Pydantic Settings, and PlatformDirs. Don't search the working tree.

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

No `.env`, project files, or Pydantic file-secret sources.

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
# File: src/pixgen/config/models.py

from pathlib import Path

from pydantic import BaseModel, Field


class Defaults(BaseModel):
    image_model: ModelId | None = None
    video_model: ModelId | None = None


class GenerationSettings(BaseModel):
    output_dir: Path | None = None
    wait_timeout: float = Field(default=600.0, gt=0)
    wait_interval: float = Field(default=3.0, gt=0)
```

```python
# File: src/pixgen/config/loader.py

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


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

`toml_file` goes to `TomlConfigSettingsSource` inside
`settings_customise_sources`, not on the class-level `SettingsConfigDict`.
Class-level values are evaluated at import time, so a `PIXGEN_CONFIG` override
after import would be ignored. Per-instantiation resolution keeps settings
testable without reimporting.

One path produces a `Settings` object. A helper that reads TOML and calls
`model_validate` isn't a shortcut. It bypasses environment precedence and
produces settings that disagree with `config get`.

Import `BaseSettings`, `SettingsConfigDict`, and settings sources from
`pydantic_settings`, never from `pydantic`. Use `type[...]` and `tuple[...]`, not
the deprecated-style `typing.Type` and `typing.Tuple` aliases.

If `generation.output_dir` is `None`, resolve it to the PlatformDirs data
directory's `artifacts/` child at runtime. Don't use `Path.cwd()` as a model
default.

## 7. Credentials

> Planned file: `src/pixgen/credentials.py`.

Credential resolution: no profiles.

```text
OS keyring → provider-standard environment variable → fail immediately
```

| Provider | Keyring account | Environment fallback |
| --- | --- | --- |
| Google | `google` | `GEMINI_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |

The keyring service name is `pixgen`.

```python
# File: src/pixgen/credentials.py

from enum import StrEnum
from pydantic import SecretStr


class CredentialSource(StrEnum):
    KEYRING = "keyring"
    ENVIRONMENT = "environment"


class CredentialResolver:
    def get(self, provider: str) -> SecretStr: ...
    def set(self, provider: str, value: SecretStr) -> None: ...
    def delete(self, provider: str) -> None: ...
    def source(self, provider: str) -> CredentialSource | None: ...
```

### Code Example

```python
# src/pixgen/credentials.py: keyring with environment fallback

resolver = CredentialResolver()
try:
    key = resolver.get("google")
except CredentialUnavailable:
    raise ValueError("No Google credential found in keyring or GEMINI_API_KEY")

source = resolver.source("google")
# Reports "keyring", "environment", or None. Never the value.
```

`source` returns `None` when no credential exists anywhere. It's the only
credential API that diagnostics call. `keys list`, `info`, and `doctor` report
the source, never the value.

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

Use sync SQLAlchemy 2 typed rows and SQLite. Provider network calls stay async.
Database transactions are short and never span an `await`.

### Typed rows

```python
# File: src/pixgen/storage/models.py

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

Add explicit nullability, indexes, uniqueness, and relationships in final
mappings. `provider_job_id` is unique per provider when non-null.

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

Migrations ship with the package. `database.py` builds an Alembic `Config`
programmatically and points `script_location` at the packaged migration
directory. Commands that need storage upgrade to `head` before opening a normal
session. Passive commands like `info` inspect paths and current revision
without creating or migrating. `doctor` compares existing database revision to
packaged head without changing it.

`Base.metadata.create_all()` is allowed only in isolated tests that explicitly
need it; it is not the production migration mechanism.

### SQLite engine policy

Every connection enables:

```text
PRAGMA foreign_keys = ON
PRAGMA journal_mode = WAL
PRAGMA busy_timeout = 5000
```

### The storage seam

Module-level functions in `storage/generations.py` take an explicit `Session`:

```python
# File: src/pixgen/storage/generations.py

def insert_pending(session: Session, request: GenerationRequest) -> UUID: ...
def mark_running(session: Session, gen_id: UUID, provider_job_id: str) -> None: ...
def mark_failed(session: Session, gen_id: UUID, error: ErrorDetail) -> None: ...
def record_artifacts(
    session: Session,
    gen_id: UUID,
    artifacts: Sequence[ArtifactFacts],
) -> None: ...
def get_generation(session: Session, gen_id: UUID) -> GenerationRow | None: ...
def list_generations(session: Session, filters: HistoryFilters) -> Sequence[GenerationRow]: ...
```

Two small value types travel with them:

```python
# File: src/pixgen/storage/generations.py

class ArtifactFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path
    media_type: str
    size_bytes: int
    sha256: str


class HistoryFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: GenerationStatus | None = None
    since: datetime | None = None
    limit: int = Field(default=20, ge=1, le=1000)
```

### Code Example

```python
# src/pixgen/storage/generations.py: transaction lifecycle with explicit Session

with session_maker() as session:
    gen_id = insert_pending(session, request)
    session.commit()

# Later, after provider submit succeeds:
with session_maker() as session:
    mark_running(session, gen_id, provider_job_id="google-123")
    session.commit()

# After artifacts are written locally:
with session_maker() as session:
    record_artifacts(session, gen_id, artifacts)
    session.commit()
```

`ArtifactFacts` describes a file that's already written. Artifact handling
produces it, `record_artifacts` consumes it, and it projects into
`ArtifactResponse` for output: same facts, never a provider payload.
`HistoryFilters` carries parsed `generation list` options so the CLI doesn't
hand raw strings to SQL.

This is a seam, not a pattern. No repository class, DAO, unit-of-work, or
generic service layer. The previous revision forbade them in prose while listing
`storage/repository.py` in the layout, and prose wins. The objection was the
ceremony, not the boundary: a named module of typed functions gives the app
layer one import and one place to prove transaction behavior, at no cost.

Explicit `Session` makes the async rule auditable. A reader sees a session
open and close in one sync call and confirms no transaction spans an `await`.

Use short-lived `Session` scopes.

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

Submission failure updates the existing row to `failed`. Video provider job
IDs are persisted before returning. A later process loads the row, selects the
provider, polls the stored interaction ID, and completes artifact handling.

Persist sanitized prompts, parameters, local paths, statuses, timestamps, safe
errors, and local artifact facts. Never persist credentials, headers, signed
URLs, complete provider responses, or media.

## 9. Machine contract

> Planned file: `src/pixgen/output.py`.

Every JSON response is a Pydantic model with:

```python
schema_version: Literal[1] = 1
```

### Response-model boundary

Pixgen uses separate internal normalized results and public CLI responses.
Provider SDK and HTTP response types are implementation details. Never expose
them through the CLI, persist them as raw payloads, or treat them as part of
Pixgen's public API.

The provider/runtime boundary produces an internal `ProviderGeneration`. It
captures only provider-safe, normalized facts: the provider job ID when present,
normalized lifecycle state, candidate media awaiting persistence, optional usage
facts, and safe diagnostics. No raw responses, credentials, headers, signed
URLs, or provider-native fields without Pixgen meaning.

After artifact handling, the public contract is built from durable Pixgen facts:

```text
GenerationResponse
├── schema_version: 1
├── id: UUIDv7
├── operation, provider, model, status
├── provider_job_id: str | null
├── artifacts: tuple[ArtifactResponse, ...]
├── usage: UsageResponse | null
├── error: ErrorDetail | null
├── created_at, completed_at
└── metadata: documented provider-neutral fields only
```

`ArtifactResponse` reports final local artifact facts: absolute path, media
kind and type, byte size, SHA-256, and optional dimensions or duration. No
remote URLs. `BatchResponse` reports requested, completed, and failed totals
plus ordered `GenerationResponse` entries, preserving submission order and
partial success.

The normalized lifecycle is `pending`, `running`, `completed`, `failed`, and
`cancelled`. `pending` means Pixgen accepted and recorded the request but
hasn't confirmed provider submission. `running` means a resumable or pollable
provider job exists. The others are terminal.

All public models are frozen Pydantic models with explicit snake_case
serialization. Fields where nullability carries state (like `provider_job_id`
for sync generations) are serialized as `null`, not omitted. Version 1 may add
optional fields but can't rename, remove, or change existing fields. Breaking
changes need a new schema version.

`BatchResponse` covers `--count` and `--variants`. `GenerationListResponse`
covers `generation list` with the same ordered-entries shape.

### Public response types

```python
# File: src/pixgen/core/results.py

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    media_type: str
    size_bytes: int
    sha256: str
    width: int | None = None
    height: int | None = None
    duration: float | None = None


class UsageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    image_count: int | None = None


class ErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    retryable: bool = False
    provider: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)


class GenerationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, alias_generator="snake_case")

    schema_version: Literal[1] = 1
    id: UUID
    operation: Operation
    provider: str
    model: ModelId
    status: GenerationStatus
    provider_job_id: str | None = None
    artifacts: tuple[ArtifactResponse, ...] = ()
    usage: UsageResponse | None = None
    error: ErrorDetail | None = None
    created_at: str  # RFC 3339 with Z
    completed_at: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class BatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    requested: int
    completed: int
    failed: int
    generations: tuple[GenerationResponse, ...]


class GenerationListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    generations: tuple[GenerationResponse, ...]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    error: ErrorDetail
```

`ErrorResponse` is the command-level envelope written to stderr. `ErrorDetail`
is also embedded in a failed `GenerationResponse` inside a batch, so one shape
serves both. `fields` is populated from the `FieldError` list produced by
`validate_request`.

`UsageResponse` reports only what a provider states plainly. Pixgen does not
compute, estimate, or display cost: prices change without notice, and a stale
number printed next to a real charge is worse than no number. Billing belongs
to the provider, as principle 6 requires.

### Code Example

```python
# src/pixgen/core/results.py: assembling a response from a stored row

from datetime import datetime

row = get_generation(session, gen_id)
artifacts = [
    ArtifactResponse(
        path=str(a.path),
        media_type=a.media_type,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
    )
    for a in row.artifacts
]

response = GenerationResponse(
    id=row.id,
    operation=row.operation,
    provider=row.provider,
    model=row.model,
    status=row.status,
    provider_job_id=row.provider_job_id,
    artifacts=tuple(artifacts),
    created_at=row.created_at.isoformat(),
    completed_at=row.updated_at.isoformat() if row.status.terminal else None,
)
```

### Metadata allowlist

`metadata` is a closed set, not a passthrough. Version 1 documents exactly
these keys:

| Key | Type | Meaning |
| --- | --- | --- |
| `revised_prompt` | `str` | The prompt the provider actually used, when it rewrites one. |
| `seed` | `int` | A provider-reported seed, when one is returned. |
| `quality` | `str` | The normalized quality tier the provider applied. |
| `finish_reason` | `str` | Why generation stopped, normalized across providers. |

An adapter that encounters anything else drops it. Adding a key is a documented
version-1 change; forwarding arbitrary provider payload is prohibited, because
it would make provider response shapes part of Pixgen's contract by accident.

### Timestamps

Every timestamp in the machine contract and in SQLite is timezone-aware UTC,
serialized as RFC 3339 with a `Z` suffix, for example `2026-09-20T14:44:03Z`. Naive
datetimes are never constructed, stored, or emitted. Local-time rendering is a
human-output concern and never appears under `--json`.

Future verification must cover JSON-schema snapshots, serialization of every
lifecycle state, secret and remote-URL sanitization, ordered partial batches,
and compatibility of documented version-1 examples.

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

Stable error codes are a `StrEnum` in `core/errors.py`, so the machine
contract and the exit-code mapping share one definition:

```python
class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_CONFIGURATION = "invalid_configuration"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    MODEL_NOT_FOUND = "model_not_found"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    GENERATION_FAILED = "generation_failed"
    GENERATION_CANCELLED = "generation_cancelled"
    TIMEOUT = "timeout"
    ARTIFACT_ERROR = "artifact_error"
    STORAGE_ERROR = "storage_error"
    INTERNAL_ERROR = "internal_error"
```

Each code maps to one exit status. The mapping is in one `cli/app.py` dictionary,
not scattered `except` clauses.

### Streams and exit codes

- Successful JSON → stdout.
- Error JSON → stderr.
- Human progress → stderr.
- Raw provider bodies and exception representations never go unsanitized.

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

Cyclopts parse failures use exit code 2. `doctor` also uses 2: any `failed`
check exits 2, while warnings and skips exit 0.

## 10. Runtime, concurrency, and package layout

Use Python 3.14 or newer. This provides standard-library `uuid.uuid7()` and is
the single documented baseline across the project.

```text
src/pixgen/
├── __init__.py
├── __main__.py
├── runtime.py
├── application.py
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
│   ├── generations.py
│   ├── artifacts.py
│   └── migrations/
├── credentials.py
├── diagnostics.py
└── output.py
```

### Module boundaries

The layout is an architectural target, not an assertion that every listed
module already exists; the divergence table at the end of this section records
what is still missing. Two entries changed in this revision:

- `application/generation.py` became the single module `application.py`. Three
  use cases plus resume do not need a package. It splits when a file gets long,
  not before.
- `storage/repository.py` became `storage/generations.py`, a module of typed
  functions over an explicit `Session`. See the storage seam in section 8.

The following index describes the package-level division of responsibility.

| Area | Status | Boundary |
| --- | --- | --- |
| Root package | Current and planned | Provides lightweight package metadata and the `python -m pixgen` delegation path; it must not construct the CLI or runtime during ordinary import. |
| `application` | Planned | Owns generation use cases: it coordinates validation, provider invocation, short persistence operations, and public-result assembly; it does not parse commands, render output, or use concrete SDK types. |
| `cli` | Partly current | Parses commands, renders human or JSON output, and maps failures to exit status; it delegates use cases through runtime and does not implement provider, storage, or core validation policy. |
| `core` | Partly current | Defines transport- and storage-free domain types, requests, results, errors, and validation. It imports no transport, no SQLAlchemy, and no adapter. |
| `providers` | Planned | Defines the internal provider protocol plus provider-specific request/response translation, curated static model records, and native-option validation; it does not expose a public plugin API. |
| `config` | Current | Resolves typed settings and platform paths; it does not resolve credentials or perform provider calls. |
| `storage` | Planned | Owns SQLite bootstrap, schema, query functions, artifact materialization, migrations, and durable generation/artifact facts; it does not hold open transactions across provider calls. |
| Runtime support | Planned | `runtime`, `credentials`, `diagnostics`, and `output` compose dependencies, resolve secrets, run health checks, and render output without leaking secrets or provider payloads. `diagnostics` owns `DoctorContext` and the check registry; `cli/system.py` stays a thin wrapper that renders results and maps them to exit status. |

`runtime.py` is the composition root. It creates only the dependencies required
by the selected command: resolved settings first, then lazy credential, storage,
provider, and application-service dependencies as needed. The application
layer, not runtime or CLI, coordinates a generation request and triggers
credential resolution only after provider-neutral validation succeeds. This
keeps `--help`, `config path`, `model list`, and passive `info` free of
credential, database, or network side effects. Do not hide construction in
global singletons.

Start each provider in one focused module. Split it into a package only after
real size or independent test seams justify the change.

The console entry point should become:

```toml
[project.scripts]
pixgen = "pixgen.cli.app:main"
```

`src/pixgen/__main__.py` delegates to that `main()` so `python -m pixgen` uses
the identical path. Neither `pixgen/__init__.py` nor `__main__.py` may import
the Cyclopts application at module scope: importing the package must not build
the CLI.

### Async and concurrency

Providers are asynchronous, Cyclopts is synchronous, and SQLAlchemy is
synchronous. One rule reconciles them:

> **Each CLI command calls `asyncio.run()` exactly once.**

```python
@image_app.command
def create(prompt: str, /, *, model: ModelId | None = None) -> None:
    response = asyncio.run(create_image(deps, request))
    render(response)
```

- `cli/*` is synchronous. It parses, calls one use case, renders, and exits.
- `application.py` is asynchronous and owns the whole lifecycle of a command.
- `providers/*` is asynchronous at the network boundary only.
- `storage/*` is synchronous and is called directly from asynchronous code.

Calling synchronous SQLite from the event loop is deliberate. Local SQLite
writes complete in well under a millisecond, there is no second client to
starve, and an executor would add a failure mode in exchange for nothing
measurable. The rule that matters is the one section 8 already states: a
`Session` opens and closes inside a single synchronous call, so no transaction
can span an `await`. Explicit sessions make that checkable by reading the code.

`--variants` bounds concurrency with `asyncio.Semaphore(4)`. Results are
reassembled by index so machine output preserves submission order regardless of
completion order. Polling uses `stamina` on reads only; submissions are never
retried.

Do not introduce `anyio`, a thread pool, or an async SQLite driver in 0.1. Each
would add a concurrency model to a program that needs one.

### Current divergence from this document

The checkout has not caught up to this specification. These gaps are tracked
scope, not surprises, and section 15 sequences their repair. See **§15 Implementation order** for the sequence these gaps are closed in, and **§16 Decisions and removals** for the reasoning behind key architectural choices.

| Area | Current | Target |
| --- | --- | --- |
| Console entry point | `pixgen = "pixgen:main"` | `pixgen = "pixgen.cli.app:main"` |
| Package import | `__init__.py` imports `cli.app` at module scope | No CLI construction on import |
| Dependencies | `sqlmodel`, `pydantic-settings[yaml]` present; `alembic`, `sqlalchemy`, `google-genai` absent | Section 10 dependency list |
| Validation module | `core/validations.py`, checks bound to `MediaReference` validators | `core/validation.py`, `validate_request(request, spec)` |
| Request union | `operation` is a bare `Operation`, so the union does not discriminate | `Literal[Operation.…]` per member |
| Request params | `dict[str, Json]` | `dict[str, JsonValue]` |
| Request base | `VideoCreateRequest` inherits `count` and `aspect_ratio` | Two-level base; video has no `count` |
| Config defaults | `Defaults` hardcodes model IDs | Both default to `None`; section 3 resolution order applies |
| Config output dir | `default_factory=Path.cwd` | `None`, resolved to the data directory at runtime |
| Config TOML source | `toml_file` evaluated at class definition | `resolve_config_path()` called inside `settings_customise_sources` |
| Config override | `PIXGEN_CONFIG` unimplemented; `loader.read_config_file` bypasses precedence | Absolute `PIXGEN_CONFIG` honored; one resolution path |
| Tests | No `tests/` directory | Section 13 layout |
| Justfile | `run: uv run app`, `type-check-ty: uv run ty check` | `uv run pixgen`, `uv run pyrefly check` |

### Runtime dependencies

Initial compatible bounds, verified against current releases on 2026-09-18:

```toml
dependencies = [
    "alembic>=1.20.0,<2",
    "cyclopts>=4.25.2,<5",
    "google-genai>=2.24.0,<3",
    "httpx2>=2.12,<3",
    "keyring>=25.7",
    "pillow>=12.3",
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

> Planned file: `src/pixgen/diagnostics.py`; commands in
> `src/pixgen/cli/system.py`.

Two commands, one distinction: **`info` reports what Pixgen already knows;
`doctor` goes and finds out.**

### `pixgen info`

`info` is passive. It resolves settings and paths and reports them. It performs
no credential lookup, no database access, no provider network call, and no
write of any kind, which is what makes it safe to run inside a shell prompt or
an agent's preamble.

```python
# File: src/pixgen/diagnostics.py

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict


class ProviderInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    credential_source: CredentialSource | None = None


class InfoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    version: str
    python_version: str
    platform: str
    config_path: Path
    config_exists: bool
    database_path: Path
    artifacts_path: Path
    keyring_backend: str | None
    default_image_model: ModelId | None
    default_video_model: ModelId | None
    providers: tuple[ProviderInfo, ...]
```

`credential_source` reports `keyring`, `environment`, or `null`. Reading the
*source* requires no secret: keyring presence is a metadata lookup and
environment presence is a key test on `os.environ`. The value is never read,
never rendered, and never logged.

The Alembic revision is deliberately absent. Determining it means opening the
database, which is an active operation and therefore a `doctor` check.

### The check contract

A check is one function. This is the whole extension model:

```python
# File: src/pixgen/diagnostics.py

from typing import Callable, Awaitable
from enum import StrEnum

type Check = Callable[[DoctorContext], Awaitable[CheckResult]]
```

Every check is `async`, including the many that never await, so the registry
stays a flat list and `doctor` honors the section 10 rule of one
`asyncio.run()` per command. `DoctorContext` carries resolved settings,
resolved paths, lazily-opened resources, and the `offline` flag; a check
receives it and returns a result rather than printing, so rendering and
policy stay separate.

```python
# File: src/pixgen/diagnostics.py

class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    category: str
    status: CheckStatus
    summary: str
    detail: str | None = None
    remedy: str | None = None


class DoctorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    status: CheckStatus
    checks: tuple[CheckResult, ...]
```

### Code Example

```python
# src/pixgen/diagnostics.py: one diagnostic check

async def check_config_parses(ctx: DoctorContext) -> CheckResult:
    try:
        config = ctx.load_config()
        return CheckResult(
            id="config.file.parses",
            category="configuration",
            status=CheckStatus.OK,
            summary="config.toml is valid TOML",
        )
    except Exception as e:
        return CheckResult(
            id="config.file.parses",
            category="configuration",
            status=CheckStatus.FAILED,
            summary="config.toml is invalid",
            detail=str(e),
            remedy="Fix the TOML syntax in ~/.config/pixgen/config.toml",
        )
```

`DoctorResponse.status` is the worst status across all checks, so a caller can
branch on one field.

`remedy` is what separates a diagnostic from a report. A check that can fail
must name the command or edit that fixes it; a check that cannot usefully
advise should not be in the registry.

### Check registry

Checks run in this order. IDs are stable and part of the machine contract:
renaming one is a breaking change to `schema_version`. `<name>` expands once
per built-in provider, so 0.1 emits `providers.google.auth` and
`providers.openai.auth`; the execution rules below write `providers.*` when a
rule applies to every expansion.

| ID | Verifies | Notes |
| --- | --- | --- |
| `config.file.parses` | `config.toml` is valid TOML | An absent file is `ok`; defaults apply |
| `config.override.absolute` | `PIXGEN_CONFIG`, if set, is absolute and exists | A relative override is `failed`, per section 6 |
| `config.keys.known` | No unknown keys | Names the offending key |
| `config.defaults.resolve` | Configured default models exist in a manifest | Unset is `warning`; set but unknown is `failed` |
| `paths.config.readable` | The config path is readable | |
| `paths.database.writable` | The database directory is writable | |
| `paths.artifacts.writable` | Temp-file probe in the artifact directory | Writes and removes one file; never creates the tree |
| `database.opens` | A connection succeeds | A missing file on a fresh install is `ok` |
| `database.revision.current` | Revision equals the packaged Alembic head | Never migrates; the remedy names the command |
| `database.pragma.wal` | `journal_mode` is WAL | |
| `database.pragma.foreign_keys` | Foreign keys are enforced | |
| `credentials.keyring.backend` | A secure backend is available | Unavailable is `warning`, since the environment fallback still works; a selected `keyrings.alt` backend is `failed` |
| `credentials.google.present` | A Google credential resolves | Reports source only |
| `credentials.openai.present` | An OpenAI credential resolves | Reports source only |
| `providers.<name>.manifest` | Every `ModelSpec` in the manifest validates | A stale `verified_at` is `warning` |
| `providers.<name>.reachable` | DNS and TLS to the provider host | Needs no credential |
| `providers.<name>.auth` | A free list-models call succeeds | `skipped` without a credential; never generates |
| `runtime.python.version` | Python 3.14 or newer | |
| `runtime.dependencies` | Installed versions satisfy the declared bounds | |

`reachable` and `auth` are separate on purpose. Folded together they cannot
distinguish a missing network from an invalid key, which is the most common
setup confusion and the one a user is least able to diagnose unaided. Separated,
the report says which.

### Execution rules

1. **A failed prerequisite skips its dependents.** If `database.opens` fails,
   the revision and pragma checks report `skipped`, not `failed`. One root cause
   produces one failure. A report where four lines are red and only one is the
   problem trains people to ignore it.
2. **`--offline` skips exactly `providers.*.reachable` and
   `providers.*.auth`.** Every other check is local and always runs. Use it in
   CI, in sandboxes, and on a plane.
3. **`doctor` never mutates.** It creates no directory, runs no migration,
   writes no configuration, and generates no media. Section 8 already requires
   this of the revision check; it applies to every check. The artifact probe is
   the one write, and it removes its own temp file.
4. **Exit 2 when any check is `failed`, otherwise 0.** Warnings and skips exit
   0. This reuses the section 9 code for configuration errors rather than
   inventing a doctor-specific status, so `pixgen doctor && deploy` works.
5. **A correct fresh install reports no failures.** No config file, no database
   file, and no artifact directory are all normal first-run states and report
   `ok` or `warning`, never `failed`. A tool that reports problems on a healthy
   install is one users learn to disbelieve.

### Rendering

Human output groups checks by category:

```text
configuration
  ✓ config.file.parses        no config file; using defaults
  ✓ config.defaults.resolve   google/gemini-3.1-flash-image

database
  ✗ database.revision.current at 0001, head is 0003
      remedy: run any storage command, or `pixgen doctor` after upgrade

providers
  ✓ providers.google.reachable
  ○ providers.openai.auth     skipped: no credential
```

Markers degrade to `[ok]`, `[!!]`, `[ w]`, and `[--]` under `--no-color` or
`NO_COLOR`. `--quiet` prints only non-`ok` checks.

`doctor --json` emits one `DoctorResponse`. The section 7 redaction rule
applies to `summary`, `detail`, and `remedy` alike: diagnostics report presence
and source, never a secret value, and never a raw provider payload.

### Deliberately absent checks

Two checks that belong in a mature `doctor` are not in the 0.1 registry:

- **`plugins.load`**: 0.1 has no plugin loader. Providers are built-in behind
  an internal protocol, per section 2.
- **`runtime.ffmpeg`**: Pixgen writes provider bytes verbatim and never
  transcodes, so no media tool is required at runtime.

Both are recorded here so the question is not reopened from memory. If either
becomes real, it is one function appended to the registry and one test, which
is the point of the check contract.

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
│   ├── diagnostics/
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

### `tests/unit/diagnostics/`

The check registry against synthetic environments. Each check is a function
returning a `CheckResult`, so each is tested in isolation with a constructed
`DoctorContext` and no real filesystem, keyring, or network.

The behaviors that matter are the cross-cutting ones:

- A clean fresh install, with no config file, no database, no artifact directory,
  produces zero `failed` checks.
- A failed prerequisite skips its dependents: a database that will not open
  yields one `failed` and three `skipped`, never four `failed`.
- `--offline` skips exactly `providers.*.reachable` and `providers.*.auth`, and
  nothing else.
- No check mutates: the filesystem and the database are byte-identical before
  and after a full run, the artifact probe file is gone, and the Alembic
  revision is unchanged when it is behind head.
- Exit status is 2 when any check failed and 0 when the worst status is
  `warning` or `skipped`.
- A credential canary never appears in `summary`, `detail`, or `remedy`.
- `InfoResponse` and `DoctorResponse` validate against their declared schemas,
  and `info` performs no credential read, database open, or network call.

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
- `validate_request` reports every independent violation in one pass, in the
  documented order.
- Format acceptance follows the resolved manifest, so the same file is valid
  for one provider and rejected for another.
- `SIGINT` during an in-flight submit persists the generation and exits 6.
- Settings resolve identically through every entry point, including an absolute
  `PIXGEN_CONFIG` override.
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
12. `doctor` reports no failures on a correct fresh install, never mutates
    local state, and exits 2 when a check genuinely fails.
13. Ruff, Pyrefly, pytest, pre-commit, and the dependency security scan pass.

The primary product criterion is:

> A human or coding agent can discover a current model, create or edit images
> through Google or OpenAI, create and resume a Google video, and consume
> explicit local artifacts using only the CLI's help and structured contracts.

## 15. Implementation order

This is sequencing, not authorization to start implementation. The detailed
task plan follows after this specification is approved. For current implementation gaps against this plan, see **§10 Current divergence from this document**; for the reasoning behind key decisions, see **§16 Decisions and removals**.

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

For current implementation gaps against these decisions, see **§10 Current divergence from this document**; for sequencing their repair, see **§15 Implementation order**.

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
| Validation split | Pydantic for shape, `validate_request(request, spec)` for policy |
| Storage seam | typed functions over an explicit `Session`; no repository class |
| Application layer | one module, `application.py` |
| Concurrency | one `asyncio.run()` per command; synchronous short SQLite calls |
| Logging | stdlib, stderr, `WARNING` default, `-v`/`-vv`, redacting filter |
| Interrupt | `SIGINT` never cancels an in-flight paid submit |
| Timestamps | timezone-aware UTC, RFC 3339 with `Z` |
| Public metadata | closed four-key allowlist; no payload passthrough |
| Cost reporting | none; usage facts only |
| Type checking | Pyrefly only |
| Diagnostics | passive `info`; active `doctor` with a registry of identified checks |
| Doctor network | probes by default; `--offline` runs local checks only |
| Doctor mutation | never; every failable check carries a `remedy` string |
| Doctor exit | 2 on any `failed` check, 0 for warnings and skips |
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
