# Project

## Summary

Pixgen is an open-source, local, bring-your-own-key CLI for generating and
editing images. People, shell scripts, CI jobs, and coding agents get one typed
command shape across OpenAI, Gemini, and OpenRouter. Pixgen calls provider APIs directly,
writes explicit local artifacts, and returns structured results.

There is no hosted service, account, proxy, billing layer, MCP server, or
daemon. The provider owns inference, moderation, quotas, billing, and remote
retention.

## What each document owns

Every fact lives in exactly one file. The others link to it.

| Document | Owns |
| --- | --- |
| [`IDEA.md`](IDEA.md) | Why Pixgen exists: the problem, the alternatives, the differentiator. |
| `PROJECT.md` | Who it is for, what is in and out of 0.1, and when to stop. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Module boundaries, data flows, and failure policy. |
| [`pixgen.md`](pixgen.md) | The complete contracts: CLI, core types, providers, configuration, machine output, exit statuses, curated catalog, and tests. |

When a fact appears in two places, the copies drift apart. Restating a contract
here would make this document wrong.

## Users

- Developers using Pixgen directly from a terminal.
- Coding agents with shell access, including Claude Code and Codex.
- Scripts and CI jobs that require deterministic JSON and exit behavior.
- Developers who use independently authenticated OpenAI, Gemini, and OpenRouter accounts.

## 0.1 scope

### Providers

- OpenAI: image creation, reference-guided creation, and image editing.
- Gemini: image creation, reference-guided creation, and image editing.
- OpenRouter: curated image models through its Images API. Create and edit
  with references per model; `meta/muse-image` is create-only.

All three are built-in adapters behind an internal protocol. There is no external
plugin API in 0.1.

### User-visible capabilities

- `image create` with optional repeated, ordered local references.
- `image edit` with one or more repeated, ordered local images.
- Repeated `--model` targets and independent `--variants` per model, run in
  parallel under a configurable limit.
- Offline curated-model discovery with `model list` and `model get`, including
  each model's parameter schema.
- Configured default model lists per operation and local execution limits.
- Credentials from `OPENAI_API_KEY`, `GEMINI_API_KEY`, and
  `OPENROUTER_API_KEY`.
- Atomic local files, versioned JSON, stable errors, and stable exit statuses.

## Primary flow

1. Resolve the explicit `--model` targets or the configured defaults.
2. Validate parameters, credentials, local inputs, and output paths for every
   target before any paid request.
3. Submit one independent request per model and variant.
4. Write each returned image atomically.
5. Return human output or one versioned JSON document.

## Technology constraints

Three constraints are scope decisions, not implementation choices:

- **Python 3.14+** as the one supported baseline.
- **Local and BYOK.** No hosted service, proxy, daemon, or account.
- **Single developer.** Anything one person can't build and maintain is out of
  scope, regardless of merit.

The dependency reading list is in [`pixgen.md`](pixgen.md) under
"Implementation references".

## Non-goals and deferred work

0.1 excludes video, masks, native provider batches, generation history and
resume, cancellation of remote jobs, OS-keyring credentials, `info` and
`doctor` commands, URL-returning providers, generic OpenAI-compatible and other
third-party providers (OpenRouter is the one built-in aggregator), external
plugins, project configuration, live model
discovery, model aliases, automatic routing or fallback, retries of paid
submissions, MCP, local inference, audio, and 3D. The deferred list is
"Nice to have" in [`pixgen.md`](pixgen.md).

## Success criterion

> A human or coding agent can discover a curated model, create or edit images
> through OpenAI, Gemini, or OpenRouter, run independent variants in parallel, and consume
> explicit local artifact paths or structured errors using only the CLI's help
> and structured contracts.

## Model catalog

The curated model IDs and the evidence behind their limits are in
[`pixgen.md`](pixgen.md) under "Curated catalog". Each provider manifest
records its own `verified_at` date. A model appearing in the catalog does not
guarantee that a particular account can use it.

## Stop conditions

- If provider differences force vendor-specific conditionals into unrelated
  core paths, keep the feature adapter-specific or defer it.
- If users converge on one provider or aggregator, stop expanding adapters and
  simplify around observed usage.
- Do not publish a plugin API until the built-in adapters prove the internal
  provider contract.
