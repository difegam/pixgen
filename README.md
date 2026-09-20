# Pixgen

Pixgen is an open-source, local, bring-your-own-key CLI for generating images
and video. It gives humans and coding agents one typed command and JSON contract
across independently authenticated Google and OpenAI accounts.

Pixgen has no hosted service or proxy. Providers own inference, billing,
moderation, quotas, and remote retention; Pixgen persists resumable local state
and writes explicit local artifacts.

## Planned 0.1 capabilities

- Google and OpenAI image creation, multi-reference creation, and editing.
- Google Gemini Omni Flash text-to-video and start-frame-to-video.
- Capability-gated native image counts and explicit concurrent variants.
- Curated model discovery with local validation before paid requests.
- Secure OS-keyring credentials with `GEMINI_API_KEY` and `OPENAI_API_KEY`
  fallback.
- UUIDv7 generation history and resumable background video.
- Atomic local artifacts and versioned JSON for agents and scripts.
- Passive diagnostics, active health checks, and one provider-neutral Agent
  Skill.

External provider plugins, Veo-specific controls, remote input URLs, automatic
routing, MCP, workflow orchestration, and local inference are deferred.

## Example interface

```bash
pixgen image create "A modern cabin beside a Norwegian fjord" \
  --model google/gemini-3.1-flash-image \
  --aspect-ratio 16:9 \
  --output cabin.png

pixgen image create "Combine the product and visual style" \
  --reference product.png \
  --reference style.png \
  --model google/gemini-3.1-flash-image \
  --output campaign.png

pixgen video create "Slow dolly toward the cabin while snow falls" \
  --start-frame cabin.png \
  --model google/gemini-omni-1.1-flash \
  --no-wait --json
```

The implementation is under development; the commands above describe the
approved 0.1 contract rather than the current placeholder executable.

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

The approved implementation plan includes repairing the current placeholder
entry point and stale `just run`/type-check recipes before feature work.

## Documentation

- [Product and implementation plan](.knowledge/pixgen.md)
- [Project scope](.knowledge/PROJECT.md)
- [Architecture](.knowledge/ARCHITECTURE.md)
- [Future ideas](.knowledge/IDEA.md)

## License

Apache-2.0 is the approved license. Adding the missing package metadata is part
of the first implementation task.
