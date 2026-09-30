# Pixgen

Pixgen is an open-source, local, bring-your-own-key CLI for generating and
editing images. It gives humans and coding agents one typed command and JSON
contract across independently authenticated Google and OpenAI accounts.

Pixgen has no hosted service or proxy. Providers own inference, billing,
moderation, quotas, and remote retention; Pixgen writes explicit local
artifacts and returns versioned JSON.

## Capabilities

- OpenAI and Google image creation, multi-reference creation, and editing.
- Capability-gated native image counts and explicit concurrent variants.
- Curated model discovery with local validation before paid requests.
- Atomic local artifacts and versioned JSON for agents and scripts.

Credentials via `GEMINI_API_KEY` and `OPENAI_API_KEY` environment variables.
Video generation, OS-keyring credentials, UUIDv7 history, resumable background
video, external provider plugins, MCP, workflow orchestration, and local
inference are deferred.

## CLI

Shared commands use canonical `provider/model` IDs and keep each selected
provider's defaults. The only shared generation parameter is the strict
`width:height` aspect ratio. Ratios are reduced to canonical form (`21:9`
becomes `7:3`) and every selected model must support the requested value.

```bash
pixgen create "A modern cabin beside a Norwegian fjord" \
  --model openai/gpt-image-2 \
  --model gemini/gemini-3.1-flash-image \
  --aspect-ratio 16:9 \
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

pixgen create "Combine the product and visual style" \
  --model gemini/gemini-3.1-flash-image \
  --reference product.png \
  --reference style.png \
  --aspect-ratio 16:9 \
  --output campaign.png
```

Use `--prompt "openai"` when the complete prompt matches a provider command
name. `pixgen model list` and `pixgen model get <provider/model>` are offline
commands; `model get` reports native schemas and supported shared ratios.
`model list` renders an interactive table by default, or `--tree`/`--json`
for a grouped tree view or machine-readable output.

The old `pixgen image ...` group and generic `--param` option were removed.
Provider-specific options belong to the provider command, while shared
multi-model calls accept only the common aspect-ratio field.

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
