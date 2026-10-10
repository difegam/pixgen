# Local image optimisation

`pixgen optimize` resizes and re-encodes a local image with Pillow. It reads the
source file and writes requested outputs on the same machine. It does not send
images to a provider or remote optimisation service. Pixgen does not optimise
generated images or provider uploads automatically, and Tinify is not included.

## Basic use

With no resize options, Pixgen creates one re-encoded copy in the source format.
By default it is named `<source>-optimized.<extension>` in the configured
generation output directory, or `./pixgen` when no output directory is
configured. An explicit output name can be selected with `--output`:

```bash
pixgen optimize photo.png
pixgen optimize photo.png --output exports/photo-copy.png
```

If the `--output` name has no extension, Pixgen adds the output format's
extension. An extension that names a different format is rejected rather than
rewritten: `--format webp --output exports/photo-copy.png` is an invalid request,
while `--format webp --output exports/photo-copy` writes
`exports/photo-copy.webp`. JPEG accepts `.jpg` or `.jpeg`. With `--format keep`
(the default outside `--web`), the output format is the source format.

Use one or more resize operations. `--fit` preserves the aspect ratio inside a
`WIDTHxHEIGHT` bound, `--cover` crops to those exact dimensions, `--width`
preserves the aspect ratio at a width, and `--height` does the same for a
height. Each option can be repeated to create multiple variants of that
operation; width and height options cannot be combined with each other.

```bash
pixgen optimize photo.png --width 800
pixgen optimize photo.png --width 800 --width 1600
pixgen optimize photo.png --fit 800x800 --cover 1200x630
```

Named variant files use `<source>-<variant>.<extension>` in the output
directory. For example, width variants are named `photo-width-800.png` and
`photo-width-1600.png`. Use `--output-dir` to choose that directory. `--output`
is for a single result; it cannot be combined with `--output-dir` or multiple
planned results.

## Website variants and encoding

`--web` adds four preset variants: a 400x400 thumbnail, 1200x630 card, 1280-pixel
wide content image, and 1920x1080 hero. The preset uses WebP at quality 82 by
default. Custom options can be added to the preset, and `--format` or
`--quality` can override its encoding defaults.

```bash
pixgen optimize photo.jpg --web --output-dir website
```

Without `--web`, the source encoding is kept by default. `--format` accepts
`keep`, `jpeg`, `png`, `webp`, or `avif`; `--quality` accepts 1 through 100 for
lossy output formats. PNG does not accept a quality override. Pixgen rejects a
JPEG conversion when the source has transparency. Encoder availability depends
on the installed Pillow build. Other source metadata is not retained.

Pixels the selected encoder cannot store are converted first:

- CMYK becomes RGB for PNG, WebP, and AVIF. With an embedded profile, the
  conversion is colour-managed into sRGB and the output carries the sRGB
  profile. JPEG output keeps CMYK and its profile.
- 16-bit greyscale stays 16-bit in PNG and is scaled to 8 bits for other formats.
- Palette images become RGB, or RGBA when they have a transparent colour.

The source ICC profile is kept when it matches the colour space the encoder
stores and dropped otherwise; for example, WebP stores greyscale as RGB, so a
greyscale profile is dropped. An unreadable profile, or a CMYK profile that
cannot be converted to sRGB, is rejected during planning.

Variants that would enlarge the source are skipped rather than upscaled. A
`--cover` target is skipped if either target dimension exceeds its corresponding
source dimension. Skips are reported as `skipped` with the reason `would
upscale`; other variants can still complete.

## Planning and safe writes

`--dry-run` checks source headers, resize and encoding options, output paths,
output directories, and existing collisions, then reports the planned outputs
without creating directories or writing files:

```bash
pixgen optimize photo.png --web --dry-run
```

It does not decode source pixels, so corrupt pixel data is only found during
execution, where it fails each variant that would have been written.

An explicit output directory must already exist, in a dry run as well as a real
one. Pass `--mkdir` to let execution create an explicit output directory and its
parents. Existing output files are
left alone and reported as an error unless `--force` is supplied:

```bash
pixgen optimize photo.png --output-dir exports --mkdir --force
```

`--force` allows replacement of existing regular output files. Pixgen rejects
an output that resolves to the input file and rejects symbolic-link output
destinations. Variants that are skipped are not checked for collisions. Writes
use a temporary file and atomic replacement.

## Results

Use `--json` for the versioned machine-readable result. Each variant reports one
of `planned` (dry-run), `completed`, `skipped`, or `failed`. Planning or source
validation errors, and a failure to create the output directory, appear as a
command-level error; a failure while decoding the source or processing one
variant is recorded on the affected variants while the others continue. Human output
lists planned or saved paths and reports skips and failures separately.

Successful runs, dry-runs, and skip-only runs exit with status 0. Invalid
requests exit 2, runs where all attempted variants fail exit 3, and mixed
success/failure runs exit 4. Command-line parsing errors retain Cyclopts' exit
status 1.

## Command syntax

The command takes a positional `SOURCE` followed by options:

```text
pixgen optimize [OPTIONS] SOURCE
```

Run `pixgen optimize --help` for the installed command's exact option names,
repeatable-option notation, defaults, and format choices. The documented
examples above use the option syntax shown by that help.
