# Project

## Summary

Pixgen is an open-source, local, bring-your-own-key CLI that gives humans and
coding agents one typed interface for generative images and video. Pixgen calls
provider APIs directly, persists resumable local generation state, and writes
explicit local artifacts.

Pixgen has no hosted service, account, proxy, billing layer, required MCP
server, or background daemon. The provider owns inference, moderation, quotas,
billing, and remote retention.

The detailed source of truth is [`pixgen.md`](pixgen.md).

## Users

- Developers using Pixgen directly from a terminal.
- Coding agents with shell access, including Claude Code and Codex.
- Scripts and CI jobs that require deterministic JSON and exit behavior.
- Developers who use independently authenticated Google and OpenAI accounts.

## 0.1 scope

### Providers

- Google: image creation, reference-guided creation, image editing, and Gemini
  Omni Flash video.
- OpenAI: image creation, reference-guided creation, and image editing.

There is no external plugin API in 0.1. Google and OpenAI are built-in adapters
behind an internal provider protocol.

### User-visible capabilities

- `image create` with optional repeated local references.
- `image edit` with repeated local images and an optional mask.
- `video create` from text or one local start frame.
- Capability-gated native image `--count`.
- Explicit concurrent image `--variants`, limited to four simultaneous
  independent paid requests.
- Curated model discovery and model-specific validation.
- Keyring credentials with `GEMINI_API_KEY` and `OPENAI_API_KEY` fallback.
- UUIDv7 generation history, background video resume, and cancellation.
- Atomic local files, versioned JSON, stable errors, and stable exit codes.
- Passive `info`, active `doctor`, and one provider-neutral Agent Skill.

## Primary flows

### Generate or edit an image

1. Resolve the explicit canonical model ID or configured image default.
2. Validate capabilities, local inputs, parameters, and output paths.
3. Resolve the provider credential from keyring or environment.
4. Create a UUIDv7 generation record.
5. Submit one provider request, or explicit bounded variant requests.
6. Write returned media atomically and persist local artifact metadata.
7. Return human output or a versioned JSON response.

### Submit and resume video

1. Validate a text-only or start-frame request for Gemini Omni Flash.
2. Create a background Google interaction.
3. Persist the Google interaction ID before returning for `--no-wait`.
4. Resume later with `generation get` or `generation wait` and the UUIDv7.
5. Download the completed result atomically and update local history.

Google background execution stores the interaction remotely. See the retention
notes and source links in [`pixgen.md`](pixgen.md).

### Diagnose setup

- `pixgen info` reports passive local runtime and path information.
- `pixgen doctor` checks configuration, paths, Alembic revision, SQLite
  pragmas, keyring, credential presence, provider authentication, and model
  manifests.

## Technology constraints

- Python 3.14+.
- Cyclopts for the CLI.
- Pydantic v2 and Pydantic Settings for typed boundaries and TOML settings.
- PlatformDirs user configuration only, with absolute `PIXGEN_CONFIG` override.
- Synchronous typed SQLAlchemy 2, SQLite, and Alembic.
- Official async `google-genai` for Google.
- Direct HTTPX2 for OpenAI images.
- Rich for human output and Stamina for safe read retries.
- Pyrefly as the sole type checker.

## Non-goals and deferred work

0.1 excludes external provider plugins, Runway, fal, Replicate, Veo, OpenAI
video, remote media URLs, project configuration, dynamic model refresh, model
aliases, automatic routing, storage maintenance commands, statistics, agent
installation, workflows, MCP, local inference, audio generation, and 3D.

## Success criteria

- Google and OpenAI independently create and edit local images.
- Google creates and resumes local video artifacts through Gemini Omni Flash.
- A background video survives CLI process termination and resumes by UUIDv7.
- Native count and independent variants have distinct, tested semantics.
- Keyring and environment credentials work independently and never leak.
- Invalid input fails before a billable call.
- All machine responses validate against versioned Pydantic models.
- The Agent Skill completes image and video workflows without provider request
  formats embedded in its instructions.
- Ruff, Pyrefly, pytest, pre-commit, and dependency security checks pass.

## Current model catalog

Model manifests in provider code will carry exact capabilities, formats,
limits, documentation URLs, and verification dates.

| Provider | Display name | Canonical ID |
| --- | --- | --- |
| Google | Nano Banana 2 | `google/gemini-3.1-flash-image` |
| Google | Nano Banana 2 Lite | `google/gemini-3.1-flash-lite-image` |
| Google | Nano Banana Pro | `google/gemini-3-pro-image` |
| Google | Gemini Omni Flash | `google/gemini-omni-1.1-flash` |
| OpenAI | GPT-Image-2.5 Sunburst | `openai/gpt-image-2.5-sunburst` |
| OpenAI | GPT-Image-2.5 Flare | `openai/gpt-image-2.5-flare` |
| OpenAI | GPT-Image-2 | `openai/gpt-image-2` |

These identifiers were checked against the official Google and OpenAI model
catalogs on 2026-09-18. Catalog presence does not guarantee access for a
particular account.

## Stop conditions

- If provider differences force vendor-specific conditionals into unrelated
  core paths, keep the feature adapter-specific or defer it.
- If users converge on one provider or aggregator, stop expanding adapters and
  simplify around observed usage.
- Do not publish a plugin API until both built-in adapters prove the internal
  provider contract.
