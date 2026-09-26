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

## Examples

```bash
pixgen image create "A modern cabin beside a Norwegian fjord" \
  --model gemini/gemini-3.1-flash-image \
  --output cabin.png

pixgen image create "Combine the product and visual style" \
  --reference product.png \
  --reference style.png \
  --model gemini/gemini-3.1-flash-image \
  --output campaign.png

pixgen image edit "Remove the background" \
  --image cabin.png \
  --model openai/gpt-image-2 \
  --output cabin-transparent.png
```

## Installation

Once published:

```bash
uvx pixgen --help
# or
uv tool install pixgen
```

Pixgen requires Python 3.14 or newer.

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
