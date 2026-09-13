# PixGen

A command-line tool for generating and managing images.

PixGen is an open-source, local, BYOK (bring-your-own-key) CLI that gives
developers — and coding agents like Claude Code — one stable interface for
generative image and video across multiple AI providers. Traffic never
passes through a PixGen service: the provider you configure owns
inference, billing, moderation, quotas, and retention.

## Why

Providers expose incompatible model names, parameters, media roles,
authentication, uploads, polling, and result formats. PixGen normalizes
the stable parts of that surface into one CLI and JSON contract, while
preserving provider-specific capabilities through adapters — without
locking you into a single aggregator or hosted platform.

## Planned features

- Text-to-image, reference-image, text-to-video, and image-to-video
  generation across built-in Google, OpenAI, Runway, and fal adapters.
- Model and capability discovery, with local validation of known
  constraints before a request is submitted.
- Secure BYOK credentials via the OS keyring, with environment-variable
  fallback for headless use.
- Persistent, resumable asynchronous jobs — submit, exit, and resume
  later using a local generation ID.
- Explicit local artifacts and sanitized local history (no secrets ever
  persisted).
- Stable, versioned JSON output for scripting and agent use.
- A small provider plugin API for adding providers without touching core.

## Installation

Once published:

```bash
uvx pixgen --help
# or
uv tool install pixgen
```

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) and
[`just`](https://github.com/casey/just):

```bash
just init   # sync deps, install git hooks
just run    # run the CLI locally
just test   # run tests
just lint   # ruff check --fix + format
just check  # run all pre-commit hooks
```

## Learn more

Full product intent, specification, and architecture live in
[`.knowledge/`](.knowledge/):

- [`IDEA.md`](.knowledge/IDEA.md) — problem and proposed solution
- [`PROJECT.md`](.knowledge/PROJECT.md) — scope, users, goals
- [`SPEC.md`](.knowledge/SPEC.md) — functional requirements
- [`ARCHITECTURE.md`](.knowledge/ARCHITECTURE.md) — system design

## License

Apache-2.0
