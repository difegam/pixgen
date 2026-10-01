# Pixgen

Pixgen is an open-source, local, bring-your-own-key CLI for generating and
editing images. It gives humans and coding agents one typed command and JSON
contract across independently authenticated Google, OpenAI, and OpenRouter
accounts.

Pixgen has no hosted service or proxy. Providers own inference, billing,
moderation, quotas, and remote retention; Pixgen writes explicit local
artifacts and returns versioned JSON.

## Capabilities

- Create and edit images with OpenAI, Google, or OpenRouter models that
  support each operation.
- Named model groups for create commands.
- Capability-gated native image counts and explicit concurrent variants.
- Curated model discovery with local validation before paid requests.
- Atomic local artifacts and versioned JSON for agents and scripts.

Credentials use environment variables: `GEMINI_API_KEY`, `OPENAI_API_KEY`, and
`OPENROUTER_API_KEY`.
Video generation, OS-keyring credentials, UUIDv7 history, resumable background
video, external provider plugins, MCP, workflow orchestration, and local
inference are deferred.

## CLI

Shared commands use canonical `provider/model` IDs and keep each selected
provider's defaults. Root `create` accepts repeated `--model` options or a
configured `--group`. Root `edit` accepts explicit models and the common
strict `width:height` aspect ratio. Ratios are reduced to canonical form
(`21:9` becomes `7:3`) and every selected model must support the requested
value.

```bash
pixgen create "A modern cabin beside a Norwegian fjord" \
  --group product-hero \
  --output cabin.png

pixgen edit "Remove the background" \
  --image cabin.png \
  --model openai/gpt-image-2 \
  --aspect-ratio 3:2 \
  --output cabin-transparent.png
```

Provider commands expose their native Pydantic parameters as typed options and
target one provider-local model. They use the same preflight, output, timeout,
variant, and JSON rendering behaviour as shared commands.

```bash
pixgen create openai "A modern cabin beside a Norwegian fjord" \
  --model gpt-image-2 \
  --quality high \
  --size 1536x1024 \
  --output cabin.png

pixgen create gemini "A modern cabin beside a Norwegian fjord" \
  --model gemini-3.1-flash-image \
  --aspect-ratio 16:9 \
  --output cabin.png

pixgen create openrouter "A modern cabin beside a Norwegian fjord" \
  --model google/gemini-3.1-flash-image \
  --resolution 2K \
  --aspect-ratio 16:9 \
  --output cabin.png

pixgen edit openrouter "Remove the background" \
  --image cabin.png \
  --model openai/gpt-image-2.5-sunburst \
  --quality high \
  --output cabin-transparent.png

pixgen create "Combine the product and visual style" \
  --group product-hero \
  --reference product.png \
  --reference style.png \
  --output campaign.png
```

OpenRouter model IDs preserve OpenRouter's upstream model slug:

- `openrouter/google/gemini-3.1-flash-image`: create and edit with up to 14
  reference images.
- `openrouter/meta/muse-image`: create only. Edit is not currently available
  via the Images API because reference-image input is not documented for this
  model.
- `openrouter/openai/gpt-image-2.5-sunburst`: create and edit with up to 16
  reference images.

OpenRouter's model-native commands accept either the upstream slug or the full
Pixgen ID after `--model`. Reference images use OpenRouter's [Images
API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation).

`--group` and `--model` cannot be used together. Groups apply only to root
`create` commands. Provider-native commands keep their provider-specific
options.

Create a group explicitly with repeated model options:

```bash
pixgen group create product-hero \
  --model openai/gpt-image-2 \
  --model gemini/gemini-3.1-flash-image \
  --description "Models suited to product hero images" \
  --tag product \
  --tag marketing
```

Omit `--model` in an interactive terminal to fuzzy-search and multi-select
models, then enter the description and optional tags. Group names must be new;
`group create` never replaces an existing group. The command validates models
locally and writes the group to the resolved TOML configuration without using
provider credentials.

Use `--prompt "openai"` when the complete prompt matches a provider command
name. `pixgen model list` and `pixgen model get <provider/model>` are offline
commands; `model get` reports native schemas and supported shared ratios.
`model list` renders an interactive table by default, or `--tree`/`--json`
for a grouped tree view or machine-readable output.

The old `pixgen image ...` group and generic `--param` option were removed.
Provider-specific options belong to the provider command. Group descriptions
and tags are reserved for future `group list` and `group show` commands.

## Installation

Once published:

```bash
uvx pixgen --help
# or
uv tool install pixgen
```

Pixgen requires Python 3.14 or newer.

Enable shell completion for bash, zsh, or fish with:

```bash
pixgen --install-completion
```

Restart the shell, or source its RC file, for completion to take effect. See
the [cyclopts shell completion
docs](https://cyclopts.readthedocs.io/en/latest/shell_completion.html) for
manual installation and troubleshooting.

## Configuration

Set API keys in the environment (both prefixed and unprefixed names work):

```bash
OPENAI_API_KEY=sk-...        # or PIXGEN_OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...           # or PIXGEN_GEMINI_API_KEY=...
OPENROUTER_API_KEY=...      # or PIXGEN_OPENROUTER_API_KEY=...
```

Optional settings (prefix `PIXGEN_`, nested with `__`):

```bash
PIXGEN_CONFIG=/absolute/path/to/pixgen.toml
PIXGEN_GENERATION__MAX_PARALLEL_REQUESTS=4
PIXGEN_GENERATION__MAX_VARIANTS=10
PIXGEN_GENERATION__MAX_JOBS=10
PIXGEN_GENERATION__REQUEST_TIMEOUT_SECONDS=300
PIXGEN_GENERATION__OUTPUT_DIR=./output
```

Reusable create-only model groups live in the TOML configuration:

```toml
[groups.product-hero]
description = "Models suited to product hero images"
tags = ["product", "marketing"]
models = [
  "openai/gpt-image-2",
  "gemini/gemini-3.1-flash-image",
]
```

The `description` and `tags` fields are presentation metadata reserved for
future `group list` and `group show` commands. They do not affect generation.

See `.env.example` for a template. Provider credentials are never read from TOML files.

## Development

The project uses [uv](https://docs.astral.sh/uv/),
[just](https://github.com/casey/just), Ruff, Pyrefly, pytest, and pre-commit:

```bash
just init
just lint
just type-check
just test
just check
```

## Documentation

- [Product and implementation plan](.knowledge/pixgen.md)
- [Project scope](.knowledge/PROJECT.md)
- [Architecture](.knowledge/ARCHITECTURE.md)
- [Future ideas](.knowledge/IDEA.md)

## License

Apache-2.0.
