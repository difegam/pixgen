# Local image media commands

**Status:** Updated design awaiting review
**Date:** 2026-10-09
**Scope:** Inspect, sanitise, and publish one local image at a time

## Summary

Pixgen will add a root-level `media` command group for local image work:

```text
pixgen media inspect IMAGE
pixgen media sanitize IMAGE
pixgen media publish IMAGE
```

`inspect` reports image facts and metadata categories without changing files. `sanitize` writes a private derivative with normalized pixels and no source metadata. `publish` writes a derivative with only configured rights metadata in standard XMP fields.

The commands process one static PNG, JPEG, or WebP image at a time. They never modify the source. Output files are verified before Pixgen promotes them atomically.

## Goals

- Report image format, dimensions, colour mode, alpha, orientation, profile state, and metadata categories without exposing sensitive values.
- Create private derivatives that apply EXIF orientation, convert pixels to sRGB, and remove source metadata.
- Create public derivatives that contain only configured rights metadata.
- Keep CLI parsing, rendering, and file output at the existing Pixgen boundaries.
- Reuse the shared image transforms added for local optimisation rather than creating a second image codec pipeline.

## Out of scope

- Audio, video, animated images, and multi-file batch operations.
- Multi-size output sets, which belong to `pixgen optimize`.
- Metadata passthrough or a general metadata editing language.
- AI authorship detection or inferred provenance.
- Writing prompts, prompt-writer names, or AI provenance fields.
- C2PA signing, certificate management, or trust-list verification.

## Commands

### `media inspect`

```text
pixgen media inspect IMAGE [--json]
```

The command reads one image and writes no files. It reports:

- decoded format, MIME type, dimensions, byte size, colour model, and alpha presence;
- EXIF orientation and whether pixels are oriented for display;
- presence of EXIF, GPS, IPTC, XMP, comments, embedded profiles, and C2PA data;
- known AI metadata categories as unverified metadata claims.

The result never includes GPS coordinates, prompts, arbitrary metadata values, or profile contents.

### `media sanitize`

```text
pixgen media sanitize IMAGE [--output PATH] [--format keep|png|jpeg|webp] [--force] [--mkdir] [--json]
```

The command creates a private derivative named `<source>-sanitized.<extension>` in the configured generation output directory, or `./pixgen` when no directory is configured. `--output` selects one explicit path. An explicit missing parent directory requires `--mkdir`. Existing outputs require `--force` before replacement.

`keep` preserves the decoded source format when Pillow can encode it. The pipeline applies EXIF orientation, converts pixels to sRGB, removes source metadata and C2PA data, encodes the selected format, then reopens and verifies the result.

Private output carries no source ICC profile. Untagged RGB pixels use the standard sRGB interpretation. The command always re-encodes; it has no metadata-only shortcut.

### `media publish`

```text
pixgen media publish IMAGE [--output PATH] [--format keep|png|jpeg|webp] [--quality 1..100] [--force] [--mkdir] [--json]
```

The command creates a private derivative named `<source>-published.<extension>` in the configured generation output directory, or `./pixgen` when no directory is configured. `--output` selects one explicit path. An explicit missing parent directory requires `--mkdir`. Existing outputs require `--force` before replacement.

The command first applies the private sanitisation rules, then writes the configured rights fields as standard XMP metadata. It does not copy source metadata. Pixgen uses Pillow's format-specific metadata support and the shared image encoder. The implementation plan must verify the exact XMP container and round-trip for each supported output format.

`--quality` applies only to lossy formats. Pixgen rejects conversion to JPEG when the source has transparency. Multi-size and resize variants stay in `pixgen optimize`.

## Configuration

Configuration supplies defaults for local publishing. Command-line options override output settings for one invocation.

```toml
[media.publish]
format = null
quality = 85

[media.metadata]
credit_line = null
copyright_notice = null
rights_url = null
licensor_url = null
```

`MediaSettings` is a frozen, extra-forbid settings model. The first release has no AI provenance fields or inactive C2PA configuration switches. Sanitisation always applies the private profile; users cannot disable orientation or colour normalisation.

## Public metadata

`media.publish` writes only configured, non-null fields:

| Pixgen setting | XMP property |
| --- | --- |
| `credit_line` | `photoshop:Credit` |
| `copyright_notice` | `dc:rights` |
| `rights_url` | `xmpRights:WebStatement` |
| `licensor_url` | the standard PLUS Licensor URL property |

Pixgen validates URL fields before writing. It writes no IPTC IIM block in v1. It writes no arbitrary XMP properties. The implementation plan must check the licensor property URI against the IPTC/PLUS standard before coding.

Pixgen does not infer or write AI provenance in v1. `media publish` operates on an arbitrary local file and has no trusted generation context. A later design can add a trusted provenance input if Pixgen exposes one.

## Architecture

The media commands operate on local image files.

```text
src/pixgen/media/
├── models.py       # policies, inspection facts, and media result
├── inspect.py      # safe image and metadata inspection
├── metadata.py     # metadata category detection and XMP construction
├── sanitize.py     # private output policy and verification
├── publish.py      # rights metadata allowlist
└── application.py  # local command orchestration
```

Responsibilities:

- `images` owns image loading and the shared decode, orientation, colour conversion, resize, and encode functions.
- `media` owns local policy, metadata reporting, the XMP allowlist, and the media result model.
- `application` coordinates inspection, sanitisation, and publication.
- `artifacts` owns output path planning and atomic writes.
- `cli` owns Cyclopts command definitions and human/JSON rendering.
- `runtime` constructs the media application and passes it to the root CLI builder.

PR #25 adds a root-level `optimize` command and shared image transforms in `pixgen.images.transform`. The media implementation will use those functions for orientation, sRGB conversion, and clean encoding. It will not import from `pixgen.optimization` or duplicate Pillow transforms. If the PR is not merged when implementation begins, implementation must build on its branch or wait until those shared functions are available.

The CLI registers a `media` child `App` in `build_app()`. Each subcommand returns `CliOutcome` containing a single-outcome `MediaResult`. Expected `PixgenError` and validation failures use `cli_command`; `cli.render` renders the public JSON schema and a concise human summary. The result follows the existing exit statuses and does not add partial-success states.

## Data flow and invariants

Inspection follows this flow:

```text
parse command
  -> load and decode source
  -> inspect pixels and metadata containers
  -> redact all metadata values
  -> render result
```

Sanitisation and publication follow this flow:

```text
parse command and load settings
  -> validate source and output policy
  -> decode and normalise pixels
  -> remove source metadata
  -> add configured XMP fields for publish
  -> encode and reopen output
  -> verify format, pixels, and metadata
  -> atomically write output
  -> render result
```

The commands follow these invariants:

- They never modify the source.
- They do not promote output until verification succeeds.
- Private output contains no source metadata, ICC profile, or C2PA data.
- Public output contains only the configured XMP fields.
- Human and JSON output never expose raw GPS, prompt, or metadata values.
- Expected errors contain no metadata payloads or secrets.

## Results and errors

`MediaResult` has schema version `1`, operation, source path and size, and either inspection details or output path, format, dimensions, byte size, and transformation details. It contains either one successful outcome or one `PublicError`.

Validation happens before output writes:

1. Validate source existence, regular-file status, size, and supported static format.
2. Decode and inspect the source.
3. Validate format, quality, transparency, and XMP support.
4. Validate the output path, collision policy, and parent directory.
5. Encode, reopen, and verify the result.
6. Promote the verified bytes through the artifact writer.

Reuse `ErrorCode.INVALID_REQUEST` for invalid inputs and unsupported format combinations, `ErrorCode.ARTIFACT_FAILURE` for write failures, and add `ErrorCode.MEDIA_VERIFICATION_FAILED` for output verification failures. Do not add a separate media error enum.

## Testing strategy

Use local fixtures, temporary paths, and fakes. Tests make no network requests and use no credentials.

Inspection tests cover supported formats, invalid files, orientation, profiles, alpha, EXIF, GPS, IPTC, XMP, comments, C2PA markers, and sensitive-value redaction.

Sanitisation tests verify orientation pixels, sRGB output, metadata removal, source immutability, format and alpha rules, verification failures, output collisions, `--force`, `--mkdir`, and atomic writes.

Publishing tests verify each XMP property, null omission, URL validation, removal of arbitrary source fields, per-format XMP round-trips, transparent JPEG rejection, and safe output verification.

CLI and application tests cover root command registration, parsing, human and JSON results, command-level errors, read-only inspection, output defaults, settings, and file writes.

## References

- [IPTC Photo Metadata Standard 2025.1](https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html)
- [IPTC Photo Metadata Standard overview](https://iptc.org/standards/photo-metadata/iptc-standard/)
- [Pillow 12.3 JPEG XMP support](https://github.com/python-pillow/Pillow/blob/12.3.0/docs/releasenotes/11.1.0.rst)
- [Pillow PNG metadata writing](https://github.com/python-pillow/Pillow/blob/12.3.0/src/PIL/PngImagePlugin.py)
- [Cyclopts sub-apps](https://cyclopts.readthedocs.io/en/stable/vs_arguably/subcommands.html)
- [PR #25, local image optimisation](https://github.com/difegam/pixgen/pull/25)
