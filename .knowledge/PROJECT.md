# Project

## Summary

Pixgen is an open-source, local, bring-your-own-key CLI for generative images
and video. Humans and agents get one typed interface. Pixgen calls provider
APIs directly, persists resumable local generation state, and writes explicit
local artifacts.

No hosted service, account, proxy, billing layer, MCP server, or daemon. The
provider owns inference, moderation, quotas, billing, and remote retention.

## What each document owns

Every fact lives in exactly one file. The others link to it.

| Document | Owns |
| --- | --- |
| [`IDEA.md`](IDEA.md) | Why Pixgen exists: the problem, the alternatives, the differentiator. |
| `PROJECT.md` | Who it is for, what is in and out of 0.1, and when to stop. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Module boundaries, data flows, and failure policy. |
| [`pixgen.md`](pixgen.md) | The complete contracts: CLI, core types, providers, storage, machine output, tests, acceptance criteria. |

When a fact appears in two places it drifts. Restating a contract here is how
this document becomes wrong.

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

No external plugin API in 0.1. Google and OpenAI are built-in adapters behind
an internal protocol.

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
- Passive `info`, active `doctor`, one provider-neutral Agent Skill.

## Primary flows

These are the user-visible steps. The module-level flows, including
cancellation and the async boundary, are in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

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

Google background execution stores the interaction remotely. See retention notes
and source links in [`pixgen.md`](pixgen.md).

### Diagnose setup

- `pixgen info` reports passive local runtime and path information.
- `pixgen doctor` checks configuration, paths, Alembic revision, SQLite pragmas,
  keyring, credential presence, provider auth, model manifests.

## Technology constraints

Three constraints are scope decisions, not implementation choices:

- **Python 3.14+** for standard-library `uuid.uuid7()` and one baseline.
- **Local and BYOK.** No hosted service, proxy, daemon, account.
- **Single developer.** Anything one person can't build and maintain is out of
  scope, regardless of merit.

The full dependency and tooling decisions are in
[`pixgen.md`](pixgen.md) section 16.

## Non-goals and deferred work

0.1 excludes external provider plugins, Runway, fal, Replicate, Veo, OpenAI
video, remote media URLs, project configuration, dynamic model refresh, model
aliases, automatic routing, storage maintenance commands, statistics, agent
installation, workflows, MCP, local inference, audio generation, and 3D.

## Success criteria

The single product criterion:

> A human or coding agent can discover a current model, create or edit images
> through Google or OpenAI, create and resume a Google video, and consume
> explicit local artifacts using only the CLI's help and structured contracts.

The twelve testable acceptance criteria are in [`pixgen.md`](pixgen.md)
section 14.

## Model catalog

The shipped model list with canonical IDs, capabilities, and verification
dates is in [`pixgen.md`](pixgen.md) section 5. Provider code manifests carry
exact formats and limits.

IDs were re-verified against official Google and OpenAI catalogs on 2026-09-20.
Catalog presence doesn't guarantee access for a particular account.

## Stop conditions

- If provider differences force vendor-specific conditionals into unrelated
  core paths, keep the feature adapter-specific or defer it.
- If users converge on one provider or aggregator, stop expanding adapters and
  simplify around observed usage.
- Do not publish a plugin API until both built-in adapters prove the internal
  provider contract.
