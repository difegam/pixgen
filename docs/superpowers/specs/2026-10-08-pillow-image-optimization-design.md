# Pillow Image Optimization Design

**Status:** Revised design for review

**Date:** 2026-10-08

**Scope:** Explicit local image resizing and basic compression through Pillow

## Summary

Pixgen will add a standalone `pixgen optimize SOURCE` command that creates
named website-ready variants from one local image. Pillow is the only processing
engine. The command is explicit, local, and synchronous; image generation does
not invoke it automatically, and optimization runs are not persisted.

This design supersedes the hybrid Pillow/Tinify proposal in
`2026-09-19-image-optimization-design.md`. Tinify remains an evaluated future
option, but its HTTP integration, credentials, billing, diagnostics, and remote
processing are outside this implementation.

## Goals

- Create common thumbnail, social-card, content, and hero sizes from one source.
- Support several named variants in one invocation.
- Keep decoding, resizing, color handling, and encoding local through Pillow.
- Reuse Pixgen's existing CLI result, error, settings, and atomic artifact
  conventions.
- Share low-level Pillow transforms with the media subsystem instead of adding
  a second image codec pipeline.
- Make paths, no-upscale behavior, partial results, and JSON output predictable.

## Non-goals

- Tinify or any other remote optimization service.
- API credentials, network requests, service cost estimates, remote retries,
  or optimization-specific doctor network checks.
- Automatic post-generation optimization or automatic provider-upload
  preparation. Those are separate workflows with their own settings and
  designs.
- Persistent presets, directory traversal, animated images, SVG, video,
  upscaling, focal-point selection, or background removal.
- A public optimizer plugin API or optimization history in a database.

## Command

The current Pixgen CLI registers operation commands at the root, so the command
will be `pixgen optimize`, alongside `pixgen create` and `pixgen edit`.

```text
pixgen optimize SOURCE [OPTIONS]
```

Options:

```text
--web                       Expand the standard website preset
--fit WIDTHxHEIGHT          Repeatable, preserve aspect ratio within bounds
--cover WIDTHxHEIGHT        Repeatable, crop to exact dimensions
--width PIXELS              Repeatable, scale to a width
--height PIXELS             Repeatable, scale to a height
--format keep|jpeg|png|webp|avif
--quality 1..100            For lossy local encoders only
--output PATH               Valid only when one output is planned
--output-dir DIR            Destination for a named output set
--dry-run                    Validate and report without file-system changes
--mkdir
--force
--json
--quiet
--no-color
```

`SOURCE` is a local regular file. Remote URLs are not accepted.

### Custom sizes

Custom sizes use ordinary named CLI options rather than a packed
`name=size:mode` expression. Each sizing option is repeatable and accepts
positive integer dimensions. `--fit` and `--cover` accept `WIDTHxHEIGHT`;
`--width` and `--height` accept one pixel value each. Fit preserves aspect
ratio within the requested bounds; cover crops to exact dimensions using a
center crop; width and height scale proportionally. Width and height options
cannot be used together because that would imply stretching, which is not
supported.

Custom output names are derived from the operation and dimensions, for example
`fit-400x400`, `cover-1200x630`, or `width-1280`. Custom outputs are ordered
deterministically by option family (`fit`, `cover`, `width`, `height`) and then
by the order values were supplied for that option. Duplicate operation-size
pairs are rejected. `--web` keeps semantic names (`thumbnail`, `card`,
`content`, `hero`).

### Website preset

`--web` expands the following ordered set:

| Output | Transform | Default encoding |
| --- | --- | --- |
| `thumbnail` | centered crop, 400×400 | WebP, quality 82 |
| `card` | centered crop, 1200×630 | WebP, quality 82 |
| `content` | scale to width 1280 | WebP, quality 82 |
| `hero` | centered crop, 1920×1080 | WebP, quality 82 |

Explicit format and quality override preset defaults. Custom size options may
be combined with `--web`; website variants are planned first, followed by
custom outputs in deterministic option order. No preset is persisted.

If neither `--web` nor any custom size option is supplied, create one
same-dimension result named `optimized`; the default format is `keep`.

## Media and image policies

Support static PNG, JPEG, WebP, and AVIF when the installed Pillow build can
decode or encode the format. Determine capabilities from Pillow at runtime and
reject an unavailable input or output format before creating files. Pillow is
already a runtime dependency. Do not add an AVIF plugin solely to duplicate
support available from the installed Pillow build.

`--quality` applies only to lossy JPEG, WebP, or AVIF output. It is invalid for
PNG. Converting transparency to JPEG is rejected; Pixgen never invents a
background colour.

All outputs apply EXIF orientation to pixels and remove EXIF, XMP, and GPS data.
Preserve the source ICC profile when the selected Pillow encoder supports it.
The media sanitisation pipeline has a distinct policy: it converts to sRGB and
strips the source profile. Shared transform primitives must accept explicit
colour/profile policy so these workflows do not silently inherit one another's
metadata decisions.

Pixgen never upscales. A scale variant is skipped if its requested axis is
larger than the oriented source. A cover variant is skipped when its exact
target dimensions would require enlargement. Fit uses the smaller of its bounds
and source dimensions. Other valid variants continue. A plan with no runnable
variants is rejected before output, with `invalid_request`.

## Architecture

The existing CLI is root-command based. Keep parsing and rendering in
`src/pixgen/cli/optimize.py`; register the command from `cli/app.py`. Use the
existing `core/errors.py`, `core/results.py`, `cli/outcome.py`, and
`cli/render.py` contracts instead of introducing a second error or output
system.

The optimization-specific code is a small planner and application flow under
`src/pixgen/optimization/`:

```text
optimization/models.py       Request, variant, plan, and result detail types
optimization/planner.py      Parse variants, inspect facts, validate paths
optimization/application.py  Execute the plan and collect per-variant results
```

There is one engine, so do not add an `Optimizer` protocol or engine registry.
Pillow codec operations live in the shared `src/pixgen/images/transform.py`.
That module builds on `images/inspect.py` and returns encoded bytes plus image
metadata; it does not know about CLI flags, presets, or output paths.

Use `pixgen.artifacts.write_atomic(path, data, overwrite=...)` for final file
promotion. Preflight every path and collision before processing. Honour
`--mkdir` only during execution, after validation; do not create directories in
`--dry-run`. Existing destinations remain untouched unless `--force` is used,
and remain intact until a complete replacement is ready.

### Data flow

```text
parse CLI request
→ inspect source header and dimensions without loading its full pixel array
→ expand --web and merge explicit variants
→ validate formats, quality, dimensions, no-upscale rules, and all destinations
→ return the plan immediately for --dry-run
→ load normalized Pillow pixels once for execution
→ resize and encode runnable variants sequentially
→ reopen and verify each encoded result
→ atomically write successful outputs
→ return per-variant results in plan order
```

Sequential encoding bounds memory and allows successful files to remain if a
later variant fails.

## Paths, results, and errors

Default named paths are `<source-stem>-<variant>.<extension>` in the explicit
output directory or Pixgen's configured output directory. With no output
directory, follow the existing `Path.cwd() / "pixgen"` fallback. `--output` is
valid only for a single result. `--output` and `--output-dir` are mutually
exclusive. Resolve reported paths to absolute paths.

Preserve the result state order `completed`, `skipped`, or `failed`; JSON uses
the current Pixgen string schema version `"1"`. All results remain in plan
order. Skip-only runs are successful because no-upscale is an expected
planning result. A mixture of failed and completed variants is a partial
failure; successful outputs remain available.

Extend `ErrorCode` with `optimization_failed` for per-variant Pillow failures.
Use existing errors for invalid input, configuration, and artifact writes.
Integrate `OptimizeResult` with `cli/outcome.py` and `cli/render.py`. Reuse
existing exit statuses: success `0`, rejected input `2`, all variants failed
`3`, and partial variant failure `4`.

`--dry-run` validates that the source can be opened and its header metadata is
readable, plus variant grammar, format and quality compatibility, no-upscale
classification, output paths, and collisions. It does not fully decode source
pixels, write files, or create directories. A truncated/corrupt pixel payload
may therefore fail only during execution, before that variant is written.

## Tool choice

Pillow is the complete v1 processing surface: it provides local resizing,
cropping, and encoding without credentials, uploads, or per-image charges.
Tinify's automatic compression and smart cropping were evaluated as useful
optional benefits, but their remote processing, upload privacy, and usage-based
billing are outside the current scope. The earlier tool and price comparison
remains in the superseded hybrid proposal for future reference. Hosted delivery
platforms such as Cloudflare Images, ImageKit, and Cloudinary remain out of
scope because Pixgen writes local artifacts rather than hosting images.

## Testing and acceptance

Tests follow the current repository layout and use `tests/factories.py`,
`tmp_path`, and local Pillow fixtures. No test contacts an external service.

- Planner tests cover preset expansion and ordering, option parsing, format
  capability checks, alpha-to-JPEG rejection, dimensions, no-upscale skips,
  output naming, collision handling, and side-effect-free dry runs.
- Image tests cover one decode per invocation, scale/fit/centered-cover
  dimensions, orientation, metadata stripping, ICC policy, quality defaults,
  and format round trips for available encoders.
- Application tests cover sequential processing, ordered results, partial
  failures, and preserving completed outputs.
- CLI tests cover `pixgen optimize --help`, `--json`, `--mkdir`, `--force`,
  `--dry-run`, exact exit statuses, and stdout/stderr separation.
- Shared transform tests pin the privacy profile used by `media sanitize` and
  verify that optimization's ICC-preservation policy remains explicit.

The feature is accepted when `pixgen optimize SOURCE --web` produces the four
specified WebP variants for a sufficiently large static source, small sources
are never enlarged, formats and metadata meet this policy, dry-run has no file
system side effects, and all outputs use the existing atomic artifact path.

## Deferred alternatives

### Tinify

Tinify can remain a future explicit remote engine if users later need stronger
automatic compression or content-aware thumbnails. Adding it requires a new
design for network authorization, privacy disclosure, billable operation
accounting, credentials, failure/retry behavior, and remote contract tests. It
does not belong in this Pillow-only implementation.

### Hosted image services

Cloudflare Images, ImageKit, and Cloudinary combine image transforms with
storage and CDN delivery. They are a poor fit for a command whose output is a
local file, but may be reconsidered if Pixgen takes responsibility for hosted
asset delivery.
