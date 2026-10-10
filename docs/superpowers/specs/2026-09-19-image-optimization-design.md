# Website Image Optimization Design (original hybrid proposal)

**Status:** Superseded by `2026-10-08-pillow-image-optimization-design.md`

**Date:** 2026-09-19
**Scope:** Historical proposal for `pixgen image optimize`, local Pillow processing, and optional Tinify processing

## Summary

Pixgen will add a standalone image-optimization workflow for producing named,
website-ready variants from any supported local image. The default engine is
local Pillow processing. Tinify is an explicit remote BYOK engine, integrated
through Pixgen's existing HTTPX2 stack rather than the official synchronous
Python SDK.

The command will never run implicitly after image generation. It will not
persist optimization runs in SQLite. It will produce explicit, atomic local
files and a stable human or versioned JSON result.

The approved direction is:

1. Add local resizing and basic compression with Pillow as Pixgen's default.
2. Offer Tinify as an explicit remote optimization engine for stronger
   automatic compression and smart cropping.
3. Integrate Tinify through direct HTTPX2, not its Python SDK.
4. Start with a standalone `pixgen image optimize` command. Do not silently
   optimize generated images.

## Goals

- Produce common website assets such as thumbnails, social cards, content
  images, and hero images from one local source.
- Support multiple named variants in one invocation.
- Keep the default workflow local, private, offline, and free of API charges.
- Make Tinify network use and billing explicit through `--engine tinify`.
- Reuse one local decode or one Tinify upload for a complete variant set.
- Preserve successful files when another variant is skipped or fails.
- Provide deterministic paths, stable errors, versioned JSON, and documented
  exit behavior for humans, agents, and CI.
- Preserve Pixgen's existing credential, validation, output, and security
  conventions.

## Non-goals

The first release excludes:

- Automatic optimization after image generation.
- Project or user-defined persistent variant presets.
- Directory traversal or recursive batch processing.
- Animated GIF or APNG processing.
- SVG rasterization.
- Video processing.
- Upscaling.
- User-selected focal-point coordinates.
- Background removal and arbitrary effects.
- Metadata-preservation options.
- Multiple output formats per variant.
- Cloudinary, Cloudflare Images, ImageKit, imgix, Kraken, or ShortPixel
  integrations.
- A public optimizer plugin API.
- SQLite history for optimization runs.

## User-facing command

```text
pixgen image optimize SOURCE [OPTIONS]
```

Core options:

```text
--engine local|tinify       Default: local
--variant NAME=SIZE:MODE    Repeatable named output definition
--web                       Expand the standard website preset
--format keep|jpeg|png|webp|avif
--quality 1..100            Local engine only
--output PATH               Valid only when exactly one output is planned
--output-dir DIR            Destination directory for named output sets
--dry-run                    Validate and report the plan without side effects
--force
--mkdir
--json
--quiet
--no-color
```

`SOURCE` is a local regular file. Remote input URLs remain out of scope.

### Variant grammar

The repeatable `--variant` option uses these forms:

```text
NAME=WIDTHxHEIGHT:MODE
NAME=WIDTHw:scale
NAME=HEIGHTh:scale
```

Examples:

```text
thumbnail=400x400:cover
card=1200x630:cover
content=1280w:scale
portrait=900h:scale
hero=1920x1080:fit
```

Variant names must match `[a-z][a-z0-9-]*`. Width and height are positive
integers. `scale` accepts exactly one dimension. `fit`, `cover`, and `thumb`
require both dimensions. `thumb` is supported only by the Tinify engine.

The command rejects duplicate explicit variant names. A variant may replace a
same-named entry supplied by `--web`, but two explicit definitions of the same
name are an input error.

### Website preset

`--web` expands to this ordered plan:

```text
thumbnail=400x400:cover
card=1200x630:cover
content=1280w:scale
hero=1920x1080:cover
format=webp
quality=82                # local engine only
```

Explicit options override preset defaults:

- An explicit `--format` replaces the preset WebP format.
- An explicit `--quality` replaces local quality 82.
- An explicit variant with a preset name replaces that entry in its original
  position.
- A new explicit variant is appended in command-line order.

This behavior makes the shortcut transparent and customizable without adding
project configuration.

### Same-dimension optimization

If neither `--web` nor `--variant` is supplied, the command performs
same-dimension optimization. It plans one result named `optimized`. The default
format outside `--web` is `keep`.

### Output paths

Named outputs use:

```text
<source-stem>-<variant>.<extension>
```

For example:

```text
photo-thumbnail.webp
photo-card.webp
photo-content.webp
photo-hero.webp
```

`--output` is accepted only when exactly one output is planned. Multiple
outputs use `--output-dir` or Pixgen's standard generated artifact location.

Existing path rules apply:

- Never overwrite without `--force`.
- Never create a missing parent directory without `--mkdir`.
- Validate all runnable output collisions and parents before processing.
- Report absolute artifact paths.
- Write to temporary sibling files, flush and fsync them, then atomically
  replace final destinations.
- With `--force`, leave the previous destination untouched until its complete
  replacement is ready for atomic promotion.

## Supported media and metadata policy

The first release supports static PNG, JPEG, WebP, and AVIF input and output.
The planner validates the decoded format rather than trusting only the file
extension. Generated extensions follow the decoded/planned output format, not
an untrusted source suffix.

`--quality` is valid only for local JPEG, WebP, and AVIF output. It is rejected
for PNG and for the Tinify engine. Converting an image with transparency to
JPEG is rejected because background flattening is outside the first-release
contract; Pixgen never chooses an implicit background color.

For every produced image, Pixgen will:

1. Apply EXIF orientation to the pixels.
2. Remove EXIF, XMP, and GPS metadata by default.
3. Retain the ICC color profile when the selected engine and output encoder
   support it without another lossy re-encode. The local engine preserves it;
   Tinify does not document ICC preservation, so remote results do not promise
   it.

The planner reads EXIF orientation before dimensions are finalized. The local
engine transposes decoded pixels directly. Because Tinify's public API does not
document an orientation guarantee, the Tinify engine creates one local,
orientation-normalized and metadata-stripped staged source when the orientation
is not the identity value, then uploads that staged source once. This can add a
local re-encode for an EXIF-rotated JPEG, but it avoids emitting incorrectly
oriented variants. Sources whose orientation is already normalized are uploaded
as-is to avoid an unnecessary generational re-encode.

Choosing `--engine tinify` therefore authorizes sending the source file and any
metadata embedded in an already normalized source to Tinify. Output metadata is
still governed by the policy above. Before atomic promotion, Pixgen reopens
every staged output and verifies its decoded format, dimensions, static-image
status, and absence of EXIF, XMP, and GPS data. A nonconforming artifact fails
instead of being promoted.

Pixgen never upscales. The planner computes the resize scale factor from decoded
dimensions: `scale` skips when its requested axis exceeds the source; `cover`
skips when exact target dimensions require a scale factor above one; and `fit`
uses the smaller of its bounds and the source dimensions. A variant that cannot
meet its requested contract without enlargement is marked `skipped`. Other
valid variants continue. If every variant is skipped, processing does not start
and the command returns `invalid_request` with exit code 2.

## Tool evaluation and decision

Pricing below is a September 2026 snapshot and must be treated as provider
configuration, not a constant embedded in Pixgen.

| Tool | Current cost model | Main benefit | Main mismatch for Pixgen |
| --- | --- | --- | --- |
| Pillow | Open source; no per-image fee | Private, offline, deterministic local resizing and encoding | No provider-trained smart crop; compression is encoder-driven rather than automatically tuned per image |
| Tinify | 500 compressions/month free; then $0.009 for the next 9,500 and $0.002 for the next 10,000 | Focused optimization API, strong automatic compression, resize/convert, and smart thumbnail cropping | Remote upload, per-operation billing, and provider-chosen quality |
| Kraken.io | 100 MB test quota; plans start at $5/month for 500 MB of source images, with $5 per extra GB on that tier | Direct optimization API with lossy/lossless modes, resize, and conversion | Subscription and source-byte quota are less attractive for occasional Pixgen use; no local-first benefit |
| Cloudflare Images | 5,000 unique transformations/month free; paid transformations are $0.50 per 1,000 beyond that; storage and delivery are separate | Very low transformation cost plus edge caching and dynamic delivery | Best as hosted delivery infrastructure tied to a Cloudflare zone, not a CLI that materializes local artifacts |
| ImageKit | Free tier includes 20 GB delivery and 3 GB DAM storage; Lite is $9/month with 40 GB delivery, then $0.50/GB | Broad transformation, DAM, CDN, and responsive delivery platform | Billing and architecture center on hosted storage and delivery rather than one-shot local files |
| Cloudinary | Credit-based platform; one credit represents 1,000 image/video transformations or 1 GB storage, with plan-specific monthly credit limits | Deep transformation surface, DAM, AI features, and mature CDN delivery | Considerably broader account, storage, and delivery model than this feature requires |

Pillow and Tinify are complementary rather than interchangeable. Pillow is the
correct default because it makes resizing free, local, inspectable, and
available without configuration. Tinify is the appropriate first optional
remote engine because it adds a narrowly scoped quality benefit without making
Pixgen an asset-hosting platform. Kraken.io is the closest future direct-API
alternative. Cloudflare Images, ImageKit, and Cloudinary become compelling only
if Pixgen later takes responsibility for hosted storage or image delivery.

References:

- <https://tinify.com/pricing/api>
- <https://kraken.io/pricing>
- <https://developers.cloudflare.com/images/pricing/>
- <https://imagekit.io/plans>
- <https://cloudinary.com/pricing>

## Architecture

The feature is an internal subsystem, not a public plugin framework:

```text
src/pixgen/optimization/
├── models.py
├── planner.py
├── base.py
├── local.py
├── tinify.py
└── runner.py
```

Responsibilities:

- `models.py` defines requests, variant specifications, plans, engine
  capabilities, and versioned results.
- `planner.py` expands `--web`, merges overrides, inspects the source, applies
  no-upscale rules, validates capabilities, and resolves output paths.
- `base.py` defines a narrow, private, batch-oriented `Optimizer` protocol.
- `local.py` implements batch processing with Pillow.
- `tinify.py` implements the Tinify HTTP contract with an injected HTTPX2
  client and credential.
- `runner.py` selects the engine, owns staged files and atomic promotion, and
  aggregates ordered results.

The CLI layer parses and renders. It does not decode images, construct Tinify
payloads, or perform atomic writes.

### Core contracts

The domain model includes:

- `OptimizeRequest`: source, engine, requested variants, format, quality, and
  output policy.
- `VariantSpec`: name, width, height, resize mode, and output format.
- `SourceInfo`: decoded format, dimensions, orientation, byte length, alpha
  presence, and safe color-profile presence metadata.
- `OptimizationPlan`: source information plus ordered runnable and skipped
  variants, resolved destinations, and a conservative remote-cost estimate.
- `VariantResult`: name, status, dimensions, MIME type, absolute output path,
  byte counts, and optional safe error.
- `OptimizeResult`: versioned top-level result with `success`, `partial`, or
  `failed` status, source byte length, and total output byte length.

The optimizer protocol receives the complete runnable batch. This preserves
the concrete efficiency requirement: Pillow decodes once, and Tinify uploads
once.

Engines write only to staged sibling destinations supplied by the runner. They
never replace final paths. The runner validates successful staged artifacts,
flushes and fsyncs them, and performs atomic promotion.

### Engine capabilities

| Capability | Local | Tinify |
| --- | --- | --- |
| Same-dimension optimization | Yes | Yes |
| `scale` | Yes | Yes |
| `fit` | Yes | Yes |
| `cover` | Yes, center crop | Yes, provider-selected crop |
| `thumb` | No | Yes, provider-selected smart thumbnail |
| Explicit quality | Yes | No; Tinify chooses quality |
| PNG/JPEG/WebP/AVIF | Yes | Yes |
| Offline | Yes | No |
| Credential | None | Keyring or `TINIFY_API_KEY` |

The common `cover` contract guarantees size and aspect behavior, not identical
crop focus across engines.

## Data flow

```text
parse CLI
→ expand --web and merge explicit variants
→ inspect decoded source format, dimensions, orientation, and metadata
→ validate engine capabilities and every destination
→ classify no-upscale variants as skipped
→ resolve Tinify credentials only for engine=tinify
→ execute one batch through the chosen engine
→ write each completed result to a staged sibling file
→ validate, flush, fsync, and atomically promote successful outputs
→ aggregate results in planned order
→ render human or versioned JSON output
```

Optimization is synchronous from the user's perspective and is not written to
SQLite. It has no resume or cancellation contract.

## Local engine

Pillow is a required runtime dependency. The local engine:

- Opens and decodes the source once per invocation.
- Normalizes orientation before dimension planning and cropping.
- Reuses the normalized source for every variant.
- Uses high-quality resampling for downscaling.
- Uses proportional scaling for `scale`.
- Uses contain-style bounds for `fit`.
- Uses a centered exact crop for `cover`.
- Encodes the requested output format to each staged destination.
- Applies explicit quality only to formats that support it.
- Uses WebP quality 82 for the `--web` preset unless overridden.
- Processes local variants sequentially from the shared decoded image to bound
  peak memory.

The implementation must not promise exact byte-for-byte output or a fixed
compression percentage across Pillow or encoder versions.

## Tinify engine

Tinify is integrated through direct HTTPX2. Pixgen does not add the `tinify`
Python package or `requests`.

The flow is:

1. Resolve the API key from Pixgen's existing keyring-first credential system,
   falling back to `TINIFY_API_KEY`.
2. If EXIF orientation is non-identity, create the single normalized staged
   upload described by the metadata policy; otherwise use the original bytes.
3. Upload those source bytes with `POST https://api.tinify.com/shrink` using
   HTTPS Basic authentication with username `api`.
4. Read the returned output `Location` and compression-count header.
5. Verify that the location uses HTTPS, the exact `api.tinify.com` host, and
   the expected output path before following it.
6. Reuse that output location for every derivative request.
7. Stream each response into its staged destination.
8. Capture the most recent authoritative monthly compression count.

After the single source upload, derivative requests may run concurrently under
a semaphore of four. Result ordering remains the plan order. A failed
derivative does not cancel or discard other completed derivatives.

Same-dimension optimization retrieves the compressed source result. A resized
variant sends its resize instruction to the output location. Format conversion
is included when the planned format differs from the source.

### Tinify retry and timeout policy

- The initial billable `POST /shrink` is never automatically retried.
- Billable derivative `POST` requests are never automatically retried.
- A lost response may represent a successful charged operation, so connection
  and 5xx ambiguity is surfaced to the caller.
- Safe result downloads may use bounded retries with jitter and
  `Retry-After`.
- Explicit connect, read, write, and pool timeouts apply to every request.

This intentionally differs from the official Tinify Python SDK, which uses a
synchronous `requests.Session`, process-global key/count state, and an
automatic retry. Direct HTTPX2 preserves Pixgen's async transport, dependency
injection, mock-transport testing, and paid-request policy.

References:

- <https://tinify.com/developers/reference/http>
- <https://tinify.com/developers/reference/python>
- <https://tinify.com/pricing/api>

## Cost visibility and dry run

Tinify documents the initial optimization as a compression and says resizing
and conversion can add compressions. Its public examples do not fully specify
how combined resize-and-convert requests are counted. Pixgen therefore will
not present a preflight estimate as an exact charge.

The planner reports `estimated_compressions_max`, a conservative upper bound
based on the requested operations. The Tinify result reports the authoritative
`compression_count_this_month` header when available.

`--dry-run`:

- Parses and validates the full request.
- Opens the local source only as needed to inspect safe format and dimension
  metadata.
- Resolves planned destinations and collision policy.
- Reports runnable and skipped variants.
- Reports the conservative Tinify compression estimate.
- Does not resolve credentials.
- Does not make network requests.
- Does not create directories or files.

No interactive billing confirmation is added. `--engine tinify` is the
explicit authorization for remote, potentially billable processing and keeps
the command usable in CI and by agents.

## Results and machine output

Variant results remain in planned order, not completion order. Each has one of
these states:

- `completed`: an atomic final file exists.
- `skipped`: the planner intentionally omitted the variant, currently because
  fulfilling it would require upscaling.
- `failed`: processing began for the variant but did not produce a final file.

Successful artifacts remain available if another variant is skipped or fails.

Example:

```json
{
  "schema_version": 1,
  "operation": "image.optimize",
  "engine": "tinify",
  "source": "/absolute/photo.png",
  "source_bytes": 4200000,
  "status": "partial",
  "requested": 4,
  "completed": 3,
  "skipped": 1,
  "failed": 0,
  "total_output_bytes": 1124000,
  "estimated_compressions_max": 9,
  "compression_count_this_month": 127,
  "variants": [
    {
      "name": "thumbnail",
      "status": "completed",
      "path": "/absolute/photo-thumbnail.webp",
      "width": 400,
      "height": 400,
      "mime_type": "image/webp",
      "output_bytes": 384000
    },
    {
      "name": "hero",
      "status": "skipped",
      "error": {
        "code": "invalid_request",
        "message": "The source is too small for this variant.",
        "retryable": false,
        "fields": {"variant": "hero"}
      }
    }
  ]
}
```

Human output uses a compact variant table with each output's byte savings
relative to the source, followed by source bytes, total output bytes, partial
status, and Tinify's monthly compression count when returned. It does not call
the aggregate source-to-all-outputs ratio a compression percentage because a
variant set legitimately contains several files.

Successful and partial JSON documents go to stdout because they may contain
usable artifact paths. Fatal preflight errors use Pixgen's existing JSON error
envelope on stderr. JSON mode emits exactly one document and no progress text.

## Errors and exit codes

Validation order is:

1. Validate the source path and decoded static format.
2. Parse and validate variants and preset overrides.
3. Validate global format and quality options.
4. Validate engine capability combinations.
5. Inspect dimensions and classify no-upscale variants.
6. Resolve every runnable output path and validate parent/collision policy.
7. Resolve the Tinify credential only if needed.
8. Start processing.

Errors reuse Pixgen's existing stable codes wherever possible:

- Invalid grammar, unsupported combinations, and an all-skipped plan use
  `invalid_request` and exit 2.
- A missing Tinify key uses `credential_unavailable` and exit 3.
- An invalid Tinify key uses `authentication_failed` and exit 3.
- Tinify rate limits, availability, and network errors use the existing
  provider/network family and exit 4 or 5.
- Local encode/decode or remote transformation failure adds
  `optimization_failed` and exits 6.
- Staging or atomic-write errors use `artifact_error` and exit 7.
- Any mixture containing a skipped or failed variant returns top-level
  `partial` and exit 6 while preserving completed outputs.

Raw provider bodies, exception representations, API keys, authorization
headers, and output URLs are sanitized before any log, human output, JSON, or
error field is created.

## Configuration and diagnostics

Tinify secrets are not settings fields and are never stored in TOML or SQLite.
They use Pixgen's existing keyring mechanism with `TINIFY_API_KEY` as the
environment fallback.

Passive `pixgen info` reports:

- Pillow availability and version.
- Locally available input/output format capabilities.
- Whether the Tinify engine is included.
- Tinify credential presence, never its value.

Active `pixgen doctor` validates Tinify authentication only when a Tinify
credential is configured or the user explicitly requests the Tinify check.
The active check mirrors Tinify's official SDK validation behavior: send an
empty `POST /shrink`, treat the expected client-data error as proof that
authentication succeeded, and never include image bytes. It is attempted once
and is not a compression operation. Passive commands do not make Tinify network
calls.

## Documentation and Agent Skill

Documentation will include:

- Local same-dimension optimization.
- Custom named variants.
- The `--web` preset and override behavior.
- Tinify setup and explicit remote use.
- Privacy implications of uploading source images.
- Tinify billing and the conservative dry-run estimate.
- Local versus Tinify resize and crop differences.
- The fact that explicit Tinify use uploads source bytes and may expose source
  metadata to the remote service even though output metadata is stripped.
- Partial-success handling for shell scripts and agents.

The provider-neutral Agent Skill will invoke `pixgen image optimize` and
interpret its stable JSON. It will not embed Tinify HTTP payloads or direct
users to the Tinify SDK.

## Testing strategy

### Planner unit tests

- `--web` expansion and stable ordering.
- Explicit preset replacement and appended custom variants.
- Duplicate explicit names.
- Variant grammar and name constraints.
- Mode and dimension rules.
- Format defaults and overrides.
- Quality validation and Tinify rejection.
- Engine capability checks, including Tinify-only `thumb`.
- Output naming and destination resolution.
- No-upscale classification and all-skipped failure.
- Collision and parent-directory preflight.
- Dry-run plans and absence of side effects.

### Local engine tests

- Source decoding occurs once for a multi-variant batch.
- `scale`, `fit`, and centered `cover` dimensions.
- Same-dimension optimization.
- WebP quality default and override.
- Orientation normalization.
- EXIF, XMP, and GPS removal.
- ICC profile retention where supported.
- Valid PNG, JPEG, WebP, and AVIF output.

Tests assert dimensions, formats, metadata policy, and decodability. They do
not assert exact bytes or compression percentages across encoder versions.

### Tinify contract tests

An injected HTTPX2 mock transport verifies:

- Basic authentication and request bodies.
- One upload per batch.
- A normalized staged upload for non-identity EXIF orientation.
- Reuse of the returned output URL.
- Derivative payloads and output formats.
- Strict output-URL validation.
- Streaming to staged destinations.
- Rejection of downloaded artifacts that violate format, dimension, static,
  or metadata guarantees.
- Compression-count capture.
- Stable error mapping and secret sanitization.
- No retry for ambiguous upload or derivative failures.
- Bounded retry only for safe reads.

### Artifact and CLI tests

- Atomic promotion and staged-file cleanup.
- Preservation of existing destinations after failed replacement.
- `--force` and `--mkdir` behavior.
- Human output and versioned JSON.
- Exit codes 0, 2, 3, 4, 5, 6, and 7 where applicable.
- Partial results preserve completed files.
- Subprocess and installed-package behavior.

### Live tests

An optional `live_tinify` test requires an explicit key, warns that it consumes
quota, and never runs in ordinary CI.

## Acceptance criteria

The feature is complete when:

1. `--web` produces the four expected WebP variants from a sufficiently large
   source.
2. Explicit variants deterministically add to or replace preset entries.
3. Small sources never upscale and report partial results correctly.
4. Local mode performs no credential lookup or network activity.
5. Tinify uploads once and reuses its returned source for every derivative.
6. Tinify `thumb` is capability-gated and local mode rejects it before work.
7. Every successful output is atomic and every failure leaves existing files
   intact.
8. Metadata and orientation behavior matches this specification.
9. Machine output validates against the versioned Pydantic models.
10. Dry-run mode has no credential, network, directory, or file-write side
    effects.
11. Ruff, Pyrefly, pytest, pre-commit, dependency security checks, and package
    installation pass.

## Alternatives considered

### Separate command paths

Branching early into independent Pillow and Tinify command implementations
would reduce initial abstraction but duplicate validation, output naming,
partial-success behavior, and tests. It was rejected in favor of a concrete
batch boundary shared by two real engines.

### Local resize followed by Tinify compression

Resizing every variant locally and uploading each derivative would make resize
semantics uniform, but it would lose Tinify upload reuse, increase remote
operations and bandwidth, and prevent effective use of Tinify smart cropping.
It was rejected.

### Tinify Python SDK

The official SDK is concise and supports Python 3.14, but it uses synchronous
`requests`, module-level key/count state, and automatic retry behavior. Direct
HTTPX2 better matches Pixgen's runtime, testing, and paid-request policies.

### Hosted delivery platforms

Cloudinary, ImageKit, imgix, and Cloudflare Images are valuable CDN and asset
platforms but introduce hosted storage, delivery URLs, and billing concepts
that conflict with Pixgen's local-artifact focus. They are not part of this
feature.
