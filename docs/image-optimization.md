# Local image optimisation

`pixgen optimize` resizes and re-encodes a local image with Pillow. It reads the
source file and writes requested outputs on the same machine. It does not send
images to a provider or remote optimisation service. Pixgen does not optimise
generated images or provider uploads automatically, and Tinify is not included.

## Basic use

With no resize options, Pixgen creates one re-encoded copy in the source format.
By default it is named `<source>-optimized.<extension>` in the configured
generation output directory, or `./pixgen` when no output directory is
configured. An explicit output file can be selected with `--output`:

```bash
pixgen optimize photo.png
pixgen optimize photo.png --output exports/photo-copy.png
```

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
on the installed Pillow build. Output carries the source ICC colour profile
when it matches the output pixel colour space; other source metadata is not
retained. Unsupported mode/format combinations and unreadable or incompatible
ICC profiles are rejected during planning. For example, CMYK-to-WebP and
16-bit PNG-to-JPEG conversions are rejected. Keep JPEG for CMYK pixels and
PNG for 16-bit greyscale pixels. Pixgen does not silently discard their profiles.

Variants that would enlarge the source are skipped rather than upscaled. A
`--cover` target is skipped if either target dimension exceeds its corresponding
source dimension. Skips are reported as `skipped` with the reason `would
upscale`; other variants can still complete.

## Planning and safe writes

`--dry-run` checks source headers, resize and encoding options, output paths,
and existing collisions, then reports the planned outputs without creating
directories or writing files:

```bash
pixgen optimize photo.png --web --dry-run
```

It does not fully decode source pixels or require missing explicit output
directories to exist. Those checks happen during execution, so a successful
dry run does not guarantee that execution will succeed.

An explicit output directory must already exist. Pass `--mkdir` to let execution
create an explicit output directory and its parents. Existing output files are
left alone and reported as an error unless `--force` is supplied:

```bash
pixgen optimize photo.png --output-dir exports --mkdir --force
```

`--force` allows replacement of existing regular output files. Pixgen rejects
an output that resolves to the input file and rejects symbolic-link output
destinations. Writes use a temporary file and atomic replacement.

## Results

Use `--json` for the versioned machine-readable result. Each variant reports one
of `planned` (dry-run), `completed`, `skipped`, or `failed`. Planning or source
validation errors appear as a command-level error; a failure while processing
one variant is recorded for that variant while the others continue. Human output
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
