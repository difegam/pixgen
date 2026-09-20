# Idea

## Problem

Coding agents such as Claude Code and Codex can execute shell tools, but
generative-media access is fragmented across provider-specific APIs,
model identifiers, authentication, media-input conventions, uploads, and
asynchronous jobs.

Higgsfield proves that a CLI can expose image, video, audio, 3D,
editing, and creative workflows to agents, but it is tied to Higgsfield
accounts, credits, and infrastructure. Open-Higgsfield-AI is open and
self-hostable but is primarily a web studio backed by Muapi.ai rather
than a provider-neutral agent CLI.

## Proposed solution

Build **PixGen**, an open-source, local, BYOK generative-media CLI for
coding agents.

PixGen provides one discoverable command and JSON contract across
providers. Users authenticate with their own provider or aggregator
credentials. Provider adapters translate PixGen requests into vendor
APIs.

## Intended users

- Developers using Claude Code, Codex, OpenCode, or similar
    shell-capable agents.
- Developers using multiple image/video providers.
- Developers who prefer BYOK over another mandatory hosted account.
- Later, users combining cloud APIs with local/self-hosted inference.

## Why this might be useful

An agent should discover providers and models, inspect capabilities, generate
media, wait for asynchronous jobs, and use local files without learning each
provider's API.

The differentiator isn't model access. It's a stable local BYOK contract across
independently authenticated providers.

## Initial capabilities

- Text-to-image and reference-image generation/editing.
- Text-to-video and image-to-video.
- Typed/multiple media references where models support them.
- Model/capability discovery and local request validation.
- Persistent asynchronous generation state and local artifacts.
- OS-keyring credentials with environment fallback.
- Stable JSON output.
- Provider plugins and provider-scoped commands. *(Both deferred in 0.1:
  providers are built-in behind an internal protocol, and there are no
  provider-scoped commands.)*
- Central root `pixgen doctor` and passive `pixgen info`.
- Claude Code Agent Skill.

## Constraints

- CLI first, no web UI in MVP.
- Local single-user tool, no PixGen hosted service.
- Secrets never go in YAML, SQLite history, logs, or output.
- Provider and model data change frequently and must stay in adapters.
- Both sync and async APIs fit one contract.
- Non-interactive operation after credentials are set up.
- Distribution works through `uvx` and `uv tool install`.
- Scope stays practical for one developer.

## Open questions

No unresolved decision blocks the MVP.

`PixGen` had no material exact-name software/package collision in
public web searches performed 2026-09-13. Actual package-index
availability is not guaranteed until registration/publishing.

## Idea backlog

Deferred: Replicate, Muapi, Black Forest Labs, Stability AI;
video-to-video/extension; upscale/inpaint/outpaint/background
removal/reframe; motion control; audio/TTS/lip sync/dubbing/voice
change/cloning; batch generation; creative workflows/skills; 3D;
persistent identity/reference elements; ComfyUI/Wan2GP/local inference;
MCP; cost/routing/fallback/benchmarking.

Not product goals: social publishing, virality platform features,
website/Cloudflare deployment, games hosting, marketplace, mobile/web
creative studios, and Adobe/browser plugins.
