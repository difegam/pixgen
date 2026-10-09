# Pixgen CLI Command Reference

Use `pixgen --help` or the relevant subcommand's `--help` when the installed
version differs from these examples. Discover model IDs at task time; the
catalogue can change between Pixgen releases.

## Discover models

Model discovery is local and does not require API credentials:

```bash
pixgen model list --json
pixgen model get openai/gpt-image-2 --json
```

Use `model get` to inspect operation parameters and supported aspect ratios.
Choose model IDs from `model list` rather than assuming an example ID is still
available.

## Create images

```bash
pixgen create "A modern cabin beside a Norwegian fjord" \
  --model openai/gpt-image-2 \
  --output output/cabin.png \
  --mkdir \
  --json
```

Run several models in one call by repeating `--model`; `--group` cannot be used
with `--model`:

```bash
pixgen create "A modern cabin beside a Norwegian fjord" \
  --model openai/gpt-image-2 \
  --model gemini/gemini-3.1-flash-image \
  --output-dir output/cabin-comparisons \
  --mkdir \
  --json
```

For multiple variants, use `--variants`. A model group can be selected with
`--group <name>` instead of listing models.

Supply create-time reference images by repeating `--reference`:

```bash
pixgen create "Combine the product and visual style" \
  --model openai/gpt-image-2 \
  --reference product.png \
  --reference style.png \
  --output output/campaign.png \
  --mkdir \
  --json
```

## Edit images

Pass the image to edit with `--image`. Repeat `--image` only when the user
wants multiple source images as edit inputs; Pixgen does not distinguish a
separate target image from a reference role in this option:

```bash
pixgen edit "Remove the background" \
  --image product.png \
  --model openai/gpt-image-2 \
  --aspect-ratio 3:2 \
  --output output/product-edited.png \
  --mkdir \
  --json
```

The selected models must support the requested aspect ratio and input images.
Check `pixgen model get <provider/model> --json` when unsure.

## Manage model groups

Create a saved group with explicit models and list groups as JSON:

```bash
pixgen group create product-hero \
  --model openai/gpt-image-2 \
  --model gemini/gemini-3.1-flash-image \
  --description "Models for product hero images" \
  --json

pixgen group list --json
```

Only create or change a group when the user requests that configuration change.

## Optimise a local image

Optimisation is local; it uses Pillow and does not call an image provider:

```bash
pixgen optimize photo.jpg --web --output-dir output/optimised --mkdir --json
```

Use `--dry-run --json` to inspect planned outputs without writing them. Do not
use `--force` unless the user asked to replace existing files.

## Read JSON results and exit status

The current CLI accepts `--json` on `create`, `edit`, `optimize`,
`model list`, `model get`, `group create`, and `group list`. Provider-native
`create` and `edit` commands also accept it. `info` does not; check installed
command help before using JSON with other commands.

Structured results include `schema_version` (currently `"1"`) and command
specific fields. For `create` and `edit`, inspect `results`: each target has a
model and variant, and either an `artifact_path` with `media_type` or a typed
`error` with `code` and `message`. The top-level `error` represents a command
rejected before any target results were produced. Warnings are non-fatal.

For `optimize`, inspect each variant's `status`: `planned`, `completed`,
`skipped`, or `failed`. A failed variant contains a typed error; a skipped
variant contains a reason. Dry runs report planned variants.

For model and group commands, inspect the top-level `error` and the command's
data fields: `models` for model lists; `model`, `parameter_schemas`, and
`shared_aspect_ratios` for model details; `groups` for group lists; and `name`
and `config_path` for group creation.

Use both the JSON and exit status:

| Exit status | Meaning | Agent action |
| --- | --- | --- |
| `0` | Success | Report completed artifacts or data. |
| `1` | CLI parse error | Read stderr/help, correct the command, and retry if appropriate. The output may not be JSON. |
| `2` | Request rejected | Report the typed error; correct the request before retrying. |
| `3` | All generation targets failed, or optimisation had failures and no completed variants | Report each target or variant error; do not claim an artifact was created. |
| `4` | Partial failure with at least one completed target or variant | Report successful artifacts and failed targets or variants separately. |

The result schema is versioned. Read fields from the installed command's result
instead of assuming a different version's shape.
