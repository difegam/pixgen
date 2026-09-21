# Reusable media and OpenAI-compatible provider proposal

Status: proposed on 2026-09-21.

## Purpose

Pixgen needs a first-class OpenAI implementation that also gives future cloud,
router, and local providers a small, honest integration path. The common unit
is not an API brand. It is a verified media-generation capability: a model
accepts particular local inputs, parameters, and output representations for a
specific operation.

This proposal keeps the CLI contract explicit. It does not add automatic
routing, fallback, dynamic model discovery, a public plugin API, or silent
media conversion.

## Current state

The intended architecture is documented in
[`.knowledge/ARCHITECTURE.md`](ARCHITECTURE.md) and
[`.knowledge/pixgen.md`](pixgen.md). The current implementation is an early
slice of that design:

- [`src/pixgen/core/models.py`](../src/pixgen/core/models.py) has media roles
  and `MediaReference`, but validates every input with Pillow. That rejects
  video inputs and identifies no MIME type.
- [`src/pixgen/core/validation.py`](../src/pixgen/core/validation.py) checks
  that a file decodes as an image. It has no shared media inspection or output
  verification.
- [`src/pixgen/providers/base.py`](../src/pixgen/providers/base.py) exposes a
  promising provider protocol, but `ProviderMedia.media_type` is an unchecked
  string and the result type does not distinguish encoded data from a fetched
  remote result.
- [`src/pixgen/core/requests.py`](../src/pixgen/core/requests.py) carries the
  provider-neutral request types. Its `params` map remains an appropriate
  escape hatch, provided each adapter parses it into typed native options.

The target described here adds narrow shared modules. Provider adapters remain
the owners of wire formats and native parameters.

## Principles

1. **Inspect bytes, not file suffixes.** A suffix may help choose a default
   output name, but validation and persisted metadata come from inspected
   content.
2. **Keep original files intact.** Preparation creates a temporary derived
   asset and records its source. No provider silently overwrites, resizes, or
   recodes the user input.
3. **Make conversion explicit.** A request or a provider preparation rule must
   authorize a conversion. A model that only accepts PNG does not make a JPEG
   valid by accident.
4. **Use model manifests as the source of truth.** Capabilities, cardinality,
   accepted media, output types, limits, and native options belong to the exact
   model entry, not a global provider claim.
5. **Treat compatibility as evidence.** Matching `/v1` URLs does not prove
   that an endpoint supports edits, multipart uploads, base64 responses, or a
   video lifecycle.
6. **Keep paid submissions single-shot.** An ambiguous submission error is
   reported, not retried or sent to another provider.

## Proposed package layout

```text
src/pixgen/
├── core/
│   ├── media.py                 # media types, facts, limits, asset references
│   ├── requests.py              # uses MediaAssetReference, not Pillow validators
│   ├── results.py               # durable public result models
│   ├── models.py                # roles, operations, capabilities, statuses
│   └── validation.py            # manifest-based request validation
├── media/
│   ├── inspect.py               # content detection and image/video probing
│   ├── prepare.py               # explicit, temporary transformations
│   ├── encode.py                # base64, data URL, multipart helpers
│   └── artifacts.py             # result decoding, verification, atomic writes
├── providers/
│   ├── base.py                  # internal provider protocol and normalized result
│   ├── manifest.py              # model and compatibility specifications
│   ├── openai_contract.py       # Images API request/response mapping
│   ├── openai_transport.py      # configurable HTTP transport and auth
│   ├── openai.py                # native OpenAI profile and curated models
│   └── openai_compatible.py     # configured compatible profiles
├── config/
│   └── models.py                # provider endpoint/profile configuration
└── runtime.py                   # selects a profile and composes its client
```

`media/` is not an OpenAI helper. Google and every future non-compatible
provider use it for inspection, preparation, artifact validation, and atomic
writes. The OpenAI modules use it only to serialize a verified asset into the
multipart or JSON shape that their endpoint requires.

## Common media model

### Types

`MediaAssetReference` is a local input declared by a request. `MediaFacts` is
the inspected result. `PreparedMedia` is a short-lived derived file. An adapter
receives one of those objects and never re-reads, re-hashes, or guesses its
MIME type.

```python
# src/pixgen/core/media.py
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class MediaAssetReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path


class ImageFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    has_alpha: bool
    frame_count: int = Field(ge=1)
    animated: bool


class VideoFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    duration_seconds: float | None = Field(default=None, gt=0)


class MediaFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: MediaKind
    media_type: str
    byte_length: int = Field(ge=0)
    sha256: str
    image: ImageFacts | None = None
    video: VideoFacts | None = None
```

The implementation must validate the invariant that images have `image` facts,
videos have `video` facts when the selected probe can provide them, and no asset
has facts for both kinds. It should use an allowlist of MIME types rather than
accepting arbitrary `image/*` or `video/*` values.

### Inspection

`inspect_media(path)` reads enough of a local regular file to identify the
format, calculate the hash and byte length, and probe its available facts. A
Pillow-backed image probe can remain the first implementation for PNG, JPEG,
WebP, and GIF. Video probing must be a separate optional implementation because
Pillow is not a video decoder.

The inspector does not transform content. It reports an invalid or unsupported
file before submission. It replaces the current `AfterValidator` calls in
[`src/pixgen/core/models.py`](../src/pixgen/core/models.py).

### Manifest constraints

A model declares its accepted inputs by role. The shared validation code applies
the constraints after inspection and before provider submission.

```python
# src/pixgen/providers/manifest.py
from pydantic import BaseModel, Field

from pixgen.core.models import Capability, MediaRole


class MediaRoleSpec(BaseModel):
    kind: MediaKind
    accepted_media_types: frozenset[str]
    min_count: int = Field(default=0, ge=0)
    max_count: int = Field(ge=0)
    max_bytes: int | None = Field(default=None, gt=0)
    max_width: int | None = Field(default=None, gt=0)
    max_height: int | None = Field(default=None, gt=0)
    allow_animation: bool = False


class ModelSpec(BaseModel):
    canonical_id: str
    capabilities: frozenset[Capability]
    media: dict[MediaRole, MediaRoleSpec]
    output_media_types: frozenset[str]
    native_count_max: int = Field(default=1, ge=1)
```

The request validator checks role cardinality, file kind, MIME type, byte limit,
dimensions, animation, request operation, and normalized parameters. The
adapter then parses its native options. This preserves the existing rule that
provider-specific parameters do not leak into unrelated core modules.

### Preparation and encoding

Media preparation has a typed input and output. It supports conversions such as
resize, format conversion, alpha flattening, or first-frame extraction only when
the caller or a documented model preparation policy permits it.

```python
# src/pixgen/media/prepare.py
class MediaTransform(BaseModel):
    target_media_type: str | None = None
    max_width: int | None = None
    max_height: int | None = None
    flatten_alpha_on: str | None = None
    extract_first_frame: bool = False


async def prepare_media(
    source: MediaAssetReference,
    facts: MediaFacts,
    transform: MediaTransform,
) -> PreparedMedia: ...
```

`PreparedMedia` stores a temporary path, facts, source hash, and transform
record. It has a defined cleanup owner. The provider call must receive only the
prepared result when preparation occurred.

[`src/pixgen/media/encode.py`](../src/pixgen/media/encode.py) provides
streaming byte reads, base64 encoding, data-URL construction, and multipart
part construction. The helper takes verified `MediaFacts`; it never determines a
content type from the filename.

### Artifact materialization

Providers return bytes, an approved fetch URL, or a provider-specific pending
job reference. [`src/pixgen/media/artifacts.py`](../src/pixgen/media/artifacts.py)
owns download limits, decoding, media inspection, output extension selection,
and atomic writes. It records final absolute path, inspected media type, bytes,
and SHA-256.

Signed URLs are treated as transient transport input. They are not included in
JSON output, history, logs, or database rows.

## Provider boundary

The internal protocol should use structured model specifications and media
objects. A provider does not return an unchecked MIME string.

```python
# src/pixgen/providers/base.py
class ProviderMedia(BaseModel):
    model_config = ConfigDict(frozen=True)

    facts: MediaFacts | None = None
    data: bytes | None = None
    fetch_url: AnyHttpUrl | None = None


class Provider(Protocol):
    name: str

    def list_models(self) -> Sequence[ModelSpec]: ...
    def validate_params(
        self, request: GenerationRequest, spec: ModelSpec
    ) -> list[RequestIssue]: ...
    async def submit(self, request: GenerationRequest) -> ProviderGeneration: ...
    async def get(self, provider_job_id: str) -> ProviderGeneration: ...
    async def cancel(self, provider_job_id: str) -> ProviderGeneration: ...
```

`ProviderMedia` must contain exactly one delivery form: `data` or `fetch_url`.
`facts` may be absent until a URL or byte sequence has been materialized and
inspected. The runtime performs that materialization before persistence and
public output.

## OpenAI implementation and compatible endpoints

### One mapper, two profile types

The first adapter uses the OpenAI Images API as a precise contract:

- `POST /v1/images/generations` for text-to-image.
- `POST /v1/images/edits` with multipart file input for image edits and image
  references where the selected model supports them.
- `b64_json` or URL result representations, decoded or fetched by the shared
  artifact layer.

The mapper lives in
[`src/pixgen/providers/openai_contract.py`](../src/pixgen/providers/openai_contract.py).
It maps Pixgen requests into these shapes and maps responses back to
`ProviderGeneration`. It is the only code that knows OpenAI field names such as
`image[]`, `response_format`, `size`, `quality`, and `output_format`.

[`src/pixgen/providers/openai_transport.py`](../src/pixgen/providers/openai_transport.py)
is reusable HTTP infrastructure. It accepts a validated base URL, credential,
safe custom headers, timeouts, and an injected `httpx.AsyncClient`. It does not
invent a retry policy and never log authorization data.

`openai.py` creates the native profile. It has the OpenAI base URL, an
`OPENAI_API_KEY` credential resolver, curated model specs, and direct HTTP
contract tests. `openai_compatible.py` creates configured compatible profiles
using the same mapper and transport. It has no native model assumptions.

### Compatibility levels

Compatibility is a per-model declaration, not a provider-wide promise.

| Level | Meaning | Allowed Pixgen operations |
| --- | --- | --- |
| `native` | Pixgen directly verifies the provider's own contract. | Manifest-declared image operations; later video only after lifecycle tests. |
| `openai-images` | The endpoint passes Pixgen fixtures for the OpenAI Images routes. | `image-create`, and `image-edit` only if separately verified. |
| `openai-video` | The endpoint passes fixtures for a defined OpenAI-style asynchronous lifecycle. | Manifest-declared video create, get, cancel, download. |
| `partial` | The endpoint is known to accept only selected fields or operations. | Only the exact manifest declaration. |

A provider that responds to `/v1/models` or `/v1/chat/completions` has no image
compatibility by that fact alone. A declared image route does not imply edits,
multiple input files, masks, base64 output, URL downloading, or video support.

### Configuration

Provider configuration is named, so canonical model IDs remain stable and
unambiguous. Native OpenAI has its fixed `openai` provider ID. A local endpoint
could use `local/flux-dev`; a router profile could use
`router/provider/model-name` because Pixgen already splits only at the first
slash.

```toml
# config.toml
[providers.local]
kind = "openai-compatible"
base_url = "http://127.0.0.1:8080/v1"
credential_env = "LOCALAI_API_KEY"

[[providers.local.models]]
id = "flux-dev"
compatibility = "openai-images"
capabilities = ["text-to-image"]
output_media_types = ["image/png", "image/webp"]

[providers.local.models.media.reference]
kind = "image"
accepted_media_types = ["image/png", "image/jpeg"]
max_count = 1
```

The settings model in
[`src/pixgen/config/models.py`](../src/pixgen/config/models.py) validates the
provider ID, HTTPS endpoint policy, local loopback exception, header allowlist,
credential environment-variable name, and model manifests. Sensitive values do
not enter the TOML file or generated JSON.

The initial release should accept compatible profiles only through the user
configuration file. It should not add a general plugin loader or fetch a
provider's catalog dynamically.

### Compatibility assessment

| Provider family | Likely initial fit | Required verification before enabling |
| --- | --- | --- |
| Native OpenAI | Strong fit for the Images API. | Generation, edit, multipart details, output variants, errors, and each selected model. |
| OpenAI-compatible cloud inference provider | Conditional. Many endpoints emphasize text chat rather than media. | Exact image routes, accepted model IDs, input file MIME types, response form, size and count options. |
| Aggregator or router | Conditional and model-specific. | The router's advertised image and edit support, model routing behavior, pricing/failure policy, output URLs, and stable request IDs. |
| Self-hosted OpenAI-style server | Conditional. | Version-pinned endpoint behavior, local authentication, media route support, output persistence, resource/error behavior, and model constraints. |
| Non-compatible provider | Good fit for the shared media and manifest layers, but needs its own mapper. | Provider-native request/response contract and asynchronous lifecycle. |

This gives Cloudflare Workers AI, OpenRouter, LiteLLM, LocalAI, vLLM, or another
service the same evaluation method. Pixgen should not publish a support claim
until its profile and fixtures pass. The transport reuse is useful even when the
adapter must be provider-specific. As of 2026-09-21, Cloudflare Workers AI's
documented OpenAI-compatible routes cover chat completions, embeddings, and a
limited Responses API. They do not establish OpenAI Images compatibility, so
Cloudflare Workers AI is not an `openai-images` profile candidate without a
separate media endpoint and verification.

LiteLLM documents an OpenAI-style image API and an OpenAI-style video API. That
makes it a useful compatibility-test target, not evidence that every routed
model has image or video capabilities. OpenRouter and text-focused cloud
providers likewise require endpoint and model verification before inclusion.

### Video

Do not share image assumptions with video. Video requires a verified state
machine for create, poll/get, cancel, expiry, output retrieval, and resume.
The current Google background interaction implementation remains a separate
adapter path. An OpenAI-compatible video profile is added only when one target
has all of those operations, stable job IDs, and clear output retention rules.

## Error and persistence rules

The adapter maps HTTP status and safe error payload fields into existing Pixgen
codes in [`src/pixgen/core/errors.py`](../src/pixgen/core/errors.py):

| Remote condition | Pixgen code |
| --- | --- |
| Invalid field, unsupported model option, rejected media | `invalid_request` |
| Unknown model | `model_not_found` |
| Missing or rejected credential | `credential_unavailable` or `authentication_failed` |
| 429 response | `rate_limited` |
| Network or 5xx before a response | `provider_unavailable` |
| Remote job failure | `generation_failed` |
| Artifact decode, download, type, or atomic write failure | `artifact_error` |

Record the provider ID, model ID, operation, sanitized effective profile ID,
media hashes and facts, remote job ID, normalized status, and safe error data.
Never record API keys, headers, raw responses, request bodies, or signed URLs.

## Implementation order

1. Add `core/media.py` and pure manifest models. Replace image-only
   `MediaReference` validators with an explicit inspection step.
2. Add `media/inspect.py`, tests for allowed images and rejected/corrupt files,
   then `media/artifacts.py` with atomic-write and output verification tests.
3. Add `media/prepare.py` and `media/encode.py`. Start with no automatic
   transforms. Add each transform only alongside an explicit request or model
   policy and its tests.
4. Add model specs and manifest-based validation. Convert the future Google
   manifest to the same representation.
5. Implement `openai_transport.py` and `openai_contract.py` with HTTPX mock
   tests. Add native OpenAI image creation first, then edits after multipart
   tests pass.
6. Add the `openai-compatible` configured profile and fixtures for one known
   endpoint. Start with `text-to-image`; enable edits only after verification.
7. Add a video profile only after a concrete endpoint passes full lifecycle
   tests. Do not add automatic routing or fallback in this sequence.

## Tests

| Test group | Location | Covers |
| --- | --- | --- |
| Media unit tests | `tests/media/` | type detection, hashes, dimensions, corrupt files, transforms, base64, data URLs, atomic writes |
| Core validation tests | `tests/core/` | roles, cardinality, MIME allowlists, manifest limits, operation capability gates |
| OpenAI contract tests | `tests/providers/test_openai_contract.py` | generation JSON, edit multipart bodies, base64 and URL responses, safe errors |
| Compatible-profile tests | `tests/providers/test_openai_compatible.py` | endpoint configuration, declared partial support, rejected unknown fields, credentials, error mapping |
| Live opt-in tests | `tests/live/` | a named native or compatible profile, never routine CI |

Each compatible profile gets a fixture set that states the endpoint version,
model ID, successful operations, rejected operations, accepted MIME types, and
output form. A profile cannot upgrade its compatibility level without matching
fixtures and, when feasible, an opt-in live check.

## References

- [OpenAI Images API reference](https://developers.openai.com/api/docs/api-reference/images), accessed 2026-09-21. It documents image generation, edits, and base64 or URL response representations.
- [OpenAI Images edit reference](https://developers.openai.com/api/reference/resources/images/methods/edit), accessed 2026-09-21. It documents multipart image uploads and image edit fields.
- [LiteLLM image generation documentation](https://docs.litellm.ai/docs/image_generation), accessed 2026-09-21. It shows an OpenAI client configured with a custom base URL.
- [LiteLLM video documentation](https://docs.litellm.ai/docs/videos), accessed 2026-09-21. It describes an OpenAI-style asynchronous video lifecycle.
- [Cloudflare Workers AI OpenAI compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/), accessed 2026-09-21. It documents compatible chat-completions, embeddings, and limited Responses routes, not Images routes.
