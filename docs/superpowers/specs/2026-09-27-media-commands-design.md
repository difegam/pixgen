# Media sanitization and publishing commands

**Status:** Design ready for review  
**Date:** 2026-09-27  
**Scope:** Image inspection, privacy sanitization, public publishing metadata, and provider upload preparation

## Summary

Pixgen will add an image-focused `media` command group:

```text
pixgen media inspect IMAGE
pixgen media sanitize IMAGE
pixgen media publish IMAGE
```

The feature addresses two separate points in an image's lifecycle:

- Ingress sanitization protects privacy before an image is sent to an AI provider.
- Egress publishing creates a web-ready derivative with an explicit public metadata allowlist.

The original image is never modified or uploaded when sanitization is enabled. Each generated artifact is staged, reopened, verified, and atomically promoted.

The first release supports one static image per command. It does not add audio, video, recursive directory processing, or a C2PA signing system.

## Goals

- Prevent source EXIF, GPS, IPTC, XMP, comments, arbitrary profiles, and C2PA manifests from leaving the local machine during provider uploads by default.
- Normalize orientation and convert image pixels to sRGB before upload or publication.
- Provide a read-only inspection command that reports metadata and provenance signals without changing the file.
- Create a public derivative with a small, standards-based rights metadata allowlist.
- Record AI provenance only when Pixgen or a trusted existing manifest provides it.
- Reduce provider upload size and image-token use when dimensions exceed provider/model needs, without unnecessary second encodes.
- Keep commands, configuration, output, and errors small enough for humans, agents, and CI.
- Reuse the planned local image-optimization pipeline instead of creating a separate codec implementation.

## Non-goals

The first release excludes:

- Audio or video media.
- Recursive or multi-file batch processing.
- A metadata-only sanitization mode as the privacy default.
- Arbitrary metadata passthrough or a general metadata editing language.
- Automatic authorship or AI-content classification from pixels.
- Prompt storage by default.
- C2PA manifest creation, signing, certificate management, or trust-list verification.
- Provider-specific tuning flags exposed as public command options.
- A replacement for the existing planned multi-variant image optimization command.

## User-facing commands

### `media inspect`

```text
pixgen media inspect IMAGE [--json]
```

The command reads one supported image and writes no files. It reports:

- decoded format, MIME type, dimensions, byte size, color model, and alpha presence;
- orientation and whether the pixels are already normalized;
- presence and category of EXIF, GPS, IPTC, XMP, comments, embedded profiles, and C2PA;
- detected AI metadata signals, labelled as metadata claims rather than proof;
- a privacy summary, including whether the input is safe to upload under the active policy.

Raw GPS values, prompts, credentials, and arbitrary metadata payloads do not appear in human or JSON output.

### `media sanitize`

```text
pixgen media sanitize IMAGE \
  [--output PATH] \
  [--format keep|png|jpeg|webp] \
  [--json]
```

The command creates a private derivative. It never modifies the source. The default format is `keep`, which preserves the source format when the local encoder supports the requested contract.

The private profile always:

1. validates and decodes the source;
2. applies EXIF orientation to pixels;
3. converts pixels to sRGB;
4. removes EXIF, GPS, IPTC, XMP, comments, arbitrary profiles, and C2PA;
5. re-encodes the image;
6. reopens and verifies the result before promotion.

The first release has no metadata-only fast path for this command. Re-encoding gives the privacy contract one clear verification point and avoids depending on a complete list of format-specific metadata containers.

The private output relies on the standard interpretation of untagged RGB as sRGB. It does not carry the source ICC profile.

### `media publish`

```text
pixgen media publish IMAGE \
  [--output PATH] \
  [--format keep|png|jpeg|webp] \
  [--quality 1..100] \
  [--max-dimension PIXELS] \
  [--json]
```

The command creates one public derivative. It first applies the private sanitization contract, then writes only configured public metadata. It does not copy source metadata.

`--quality` applies to lossy output formats that support it. Converting an image with transparency to JPEG is rejected unless an explicit background policy is added in a later design.

The first release does not expose named output variants through `media publish`. The existing planned image-optimization workflow remains the home for multi-size derivative sets.

## Configuration

Configuration provides reusable defaults. Command-line options override them for one invocation.

```toml
[media.uploads]
sanitize = true
optimize = true
keep_temporary = false

[media.sanitize]
profile = "private"
normalize_orientation = true
normalize_srgb = true

[media.publish]
profile = "web"
format = null
quality = 85
max_dimension = null

[media.metadata]
credit_line = null
copyright_notice = null
rights_url = null
licensor_url = null

[media.provenance]
digital_source_type = "auto"
embed_ai_system = true
embed_prompt = false
embed_prompt_writer = false

[media.c2pa]
enabled = false
```

`uploads.sanitize = true` applies automatically to every local image sent to an AI provider through image references or image editing. The original path is never uploaded. A temporary sanitized file is removed by default, and JSON results report whether sanitization and provider preparation occurred.

`media.c2pa.enabled = true` fails with a clear configuration error until signing and verification are designed and implemented. The setting is reserved so that a future release does not need to redesign the configuration hierarchy.

## Public metadata mapping

`media.publish` writes only non-null configured values:

| Pixgen setting | Public metadata mapping |
| --- | --- |
| `credit_line` | IPTC Credit Line, XMP `photoshop:Credit` |
| `copyright_notice` | IPTC Copyright Notice, XMP `dc:rights` |
| `rights_url` | IPTC Web Statement of Rights, XMP `xmpRights:WebStatement` |
| `licensor_url` | PLUS/IPTC Licensor URL |

The first three mappings are defined by the IPTC Photo Metadata Standard. Licensor URL is a URL sub-field of the PLUS Licensor structure adopted by the IPTC standard. Values must be valid URLs where the target field requires a URL. Pixgen does not write arbitrary custom XMP properties.

## AI provenance policy

IPTC Photo Metadata Standard 2025.1 adds:

- AI Prompt Information;
- AI Prompt Writer Name;
- AI System Used;
- AI System Version Used.

Pixgen maps known AI system and version values to the corresponding IPTC 2025.1 fields. Prompt and prompt-writer fields remain disabled by default because prompts can contain private information.

`digital_source_type = "auto"` means:

- use trusted provenance from the current Pixgen generation operation when available;
- preserve a validated existing provenance claim only when the workflow explicitly treats it as trusted;
- otherwise omit the field.

Pixgen never labels an arbitrary local image as human-made or AI-generated based only on pixels, filenames, or a weak metadata hint.

## Provider upload preparation

Provider upload preparation is an internal step after private sanitization:

```text
source
  -> private sanitize
  -> provider/model size check
  -> downscale only when needed
  -> preserve transparency and task-relevant detail
  -> upload
```

The step is automatic when `uploads.optimize = true`. It does not expose provider-specific tuning flags in v1.

The preparation rules are:

- Do not re-encode a sanitized image when it already fits the selected provider/model requirements.
- Downscale oversized images while preserving aspect ratio.
- Use a conservative initial maximum dimension around 2048 pixels unless a provider adapter has a stricter model-specific requirement.
- Keep PNG for transparency, masks, or pixel-precise references.
- Use JPEG or WebP for opaque photographic references when reducing upload bytes helps.
- Avoid aggressive compression for text, logos, diagrams, faces, and masks.
- Report input and uploaded dimensions, format, and the reason for any transformation.
- Treat token savings as estimates until provider usage data is returned.

Compressed bytes mainly reduce upload size and latency. Image-token use is driven primarily by pixel dimensions, provider preprocessing, detail settings, and model-specific limits.

OpenAI documents PNG, JPEG, and WebP image inputs and model-specific resizing, patch, and detail behavior. GPT Image 2 processes image inputs at high fidelity, so references can consume additional image input tokens. Google documents PNG, JPEG, WebP, HEIC, and HEIF inputs; images up to 384 pixels on both axes use 258 tokens, while larger images are tiled into 768-pixel units. Gemini 3 also exposes `media_resolution`. These rules change by provider and model, so the adapter owns them rather than the public media command.

## Architecture

The feature is an internal subsystem, not a public provider-plugin API:

```text
src/pixgen/media/
├── models.py       # requests, policies, inspection, and versioned results
├── inspect.py      # format and metadata inspection
├── sanitize.py     # private pixel and metadata contract
├── publish.py      # public metadata allowlist and web output policy
├── provenance.py  # trusted AI provenance and IPTC mapping
└── provider.py    # provider-aware upload preparation
```

Expected responsibilities:

- `images` owns decoding, orientation, color conversion, format handling, and low-level metadata facts.
- `media` owns user-facing policy, metadata allowlists, provenance decisions, and result models.
- `application` invokes ingress preparation before provider requests.
- `artifacts` continues to own staged files and atomic promotion.
- `providers` receive prepared bytes and do not implement privacy policy.

The planned local optimization engine should provide the shared decode, transform, encode, and verification path. The media layer should not add a second image codec pipeline.

## Data flow and invariants

For `inspect`:

```text
parse command
  -> load and decode source
  -> inspect format, pixels, metadata, and provenance containers
  -> redact sensitive values from result
  -> render human or JSON output
```

For `sanitize` and `publish`:

```text
parse command and load policy
  -> validate source and output policy
  -> inspect source
  -> normalize pixels
  -> remove all source metadata
  -> add the publish allowlist when requested
  -> stage output
  -> reopen and verify
  -> flush, fsync, and atomically promote
  -> render result
```

The following invariants apply:

- The source is never modified.
- The source is never uploaded when ingress sanitization is enabled.
- No output is promoted before verification succeeds.
- Private outputs contain no source metadata or C2PA manifest.
- Public outputs contain only configured rights/provenance metadata.
- Temporary files are removed unless explicitly retained for diagnostics.
- Errors never include raw provider bodies, authorization headers, prompts, GPS values, or arbitrary metadata payloads.

## Results and errors

All commands support the existing human and versioned JSON rendering conventions. Results include a schema version, operation name, source path, output path when applicable, dimensions, formats, byte sizes, and transformations.

Sanitize and publish are single-output operations. They return either a verified artifact or a failure. They do not need partial-success states.

Validation happens before writes or provider requests:

1. Validate source existence, regular-file status, size, and supported static format.
2. Decode and inspect the source.
3. Validate format, quality, transparency, dimensions, and profile combinations.
4. Validate the output path and collision policy.
5. Validate provenance and C2PA configuration.
6. Prepare and write the artifact.

Existing stable error families should be reused where possible. New media-specific errors should cover unsupported metadata/format operations, media transformation failure, and verification failure. Artifact errors continue to use the existing atomic-write error family.

## Testing strategy

Tests should use local fixtures, temporary paths, injected fakes, and no real network or credentials.

Inspection tests:

- supported formats and invalid files;
- orientation, color profile, dimensions, alpha, and byte size;
- EXIF, GPS, IPTC, XMP, comments, profiles, and C2PA presence;
- redaction of sensitive values;
- stable human and JSON output.

Sanitization tests:

- orientation is applied to pixels and the orientation tag is absent;
- output pixels are sRGB;
- EXIF, GPS, IPTC, XMP, comments, arbitrary profiles, and C2PA are absent;
- source bytes and source path remain unchanged;
- output format and transparency rules are enforced;
- corrupt or nonconforming output is rejected before promotion;
- collision, `--force`, temporary-file, and atomic-write behavior.

Publishing tests:

- the four configured public fields map to the correct standard fields;
- null fields are omitted;
- invalid rights URLs are rejected;
- source metadata is not copied;
- AI system/version fields are emitted only when trusted values exist;
- prompts and prompt-writer values remain absent by default;
- arbitrary local images do not receive invented AI provenance.

Provider preparation tests:

- an already suitable image is not encoded twice;
- oversized images are downscaled with preserved aspect ratio;
- transparency and masks remain supported;
- lossy compression is avoided for protected task classes;
- provider-specific rules are selected by provider/model;
- prepared bytes contain no private source metadata;
- estimated changes are reported without claiming exact token savings.

## Standards and research references

- [IPTC Photo Metadata Standard 2025.1](https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html)
- [IPTC Photo Metadata Standard overview](https://iptc.org/standards/photo-metadata/iptc-standard/)
- [IPTC guide to licensing metadata](https://iptc.org/standards/photo-metadata/quick-guide-to-iptc-photo-metadata-and-google-images/)
- [C2PA Technical Specification](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html)
- [ImageMagick command options, profiles and `-strip`](https://imagemagick.org/command-line-options/)
- [OpenAI image generation and editing](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI image inputs and vision token behavior](https://developers.openai.com/api/docs/guides/images-vision)
- [Google Gemini image understanding](https://ai.google.dev/gemini-api/docs/image-understanding)
- [Google Gemini media resolution](https://ai.google.dev/gemini-api/docs/media-resolution)

