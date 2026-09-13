# Project

## Summary

PixGen is an open-source, local, BYOK CLI that gives coding agents one
interface for generative media across multiple AI providers. The MVP
supports image/video generation, model and capability discovery, typed
media references, persistent asynchronous jobs, local artifacts, secure
credentials, provider extensions, and machine-readable output.

PixGen never requires traffic to pass through a PixGen service. The
selected provider owns inference, billing, moderation, quotas, and
remote retention.

## Problem

Providers expose incompatible model names, parameters, media roles,
authentication, uploads, polling, and result formats. Existing products
provide model access but usually bind users to one provider/aggregator
or a hosted creative platform.

## Users

The MVP user is a developer running PixGen locally, directly or through
a coding agent with shell access.

## Goals

- Secure BYOK configuration without plaintext secrets in PixGen
    config/history.
- Agent discovery of installed providers, models, capabilities, and
    media roles.
- Stable generic image/video commands across providers.
- Resumable asynchronous generations across CLI processes.
- Explicit local artifacts.
- Provider-specific commands without root-namespace pollution.
- One root `pixgen doctor`.
- Small versioned provider plugin API.

## Non-goals

MVP excludes a web/mobile UI, hosted API/proxy/accounts/billing/storage,
automatic routing/fallback/cost optimization, MCP, audio/voice, 3D,
persistent identity, local inference, workflow engine, social
publishing, website deployment, marketplace, Adobe/browser plugins, and
a custom plugin installer.

## MVP scope

Required:

- Python `pixgen` CLI; `uvx` and `uv tool install`.
- Built-in Google, OpenAI, Runway, and fal adapters.
- Text-to-image, reference-image input, text-to-video, image-to-video.
- Typed media-reference contract capable of multiple roles/references.
- Model/capability discovery and known-constraint validation.
- SQLite generation/artifact history and resumable jobs.
- Wait/get/list/cancel where supported.
- Local artifact download.
- Pydantic Settings + YAML + PlatformDirs.
- keyring with provider environment fallback.
- stable JSON/errors/exit statuses.
- Python entry-point + Pluggy provider extensions.
- provider-scoped Cyclopts commands.
- provider-contributed checks aggregated by root `doctor`.
- passive root `info`.
- Claude Code Agent Skill.

Deferred capability families live in `IDEA.md`.

## Core user flows

### Generate media

1. Discover a model if needed.
    - Accept an explicit provider and model when supplied.
    - List installed providers and their discoverable models.
    - Filter models by requested media type and generation mode.
    - Expose model capabilities, supported parameters, and provider IDs.
    - Return a structured error when no compatible model can be selected.

2. Resolve credentials.
    - Identify the credential requirements for the selected provider.
    - Read credentials from the configured keyring entry.
    - Fall back to the provider's documented environment variable.
    - Report missing or invalid credentials without exposing secret values.
    - Keep credentials out of command output, errors, history, and job data.

3. Validate model/media compatibility.
    - Validate the requested operation: text-to-image, reference-image, text-to-video, or image-to-video.
    - Validate reference media roles, cardinality, and input locations.
    - Validate known model constraints such as dimensions, duration, aspect ratio, formats, and prompt requirements.
    - Normalize supported generic parameters into the provider request.
    - Preserve provider-specific options through the adapter escape hatch.
    - Fail before submission with stable, field-level validation errors.

4. Submit generation and persist its local ID.
    - Convert the typed generation request into the provider request.
    - Upload or reference local input media as required by the provider.
    - Submit the request and capture the provider job identifier.
    - Persist a local generation record before returning to the caller.
    - Associate the record with provider, model, operation, and request metadata while excluding secrets.
    - Handle submission failures without creating an unusable job record.

5. Wait by default or return immediately when requested.
    - Wait for completion by default using provider polling semantics.
    - Support a no-wait mode that returns the local generation ID.
    - Persist queued, running, completed, failed, and cancelled states.
    - Apply polling intervals, timeouts, and provider status translation.
    - Allow a later invocation to inspect or resume the local generation.
    - Surface provider errors with stable PixGen error categories.

6. Download completed artifacts to explicit paths.
    - Discover all output artifacts and their media types.
    - Require or derive explicit destination paths according to CLI rules.
    - Download artifacts atomically and preserve provider filenames when practical.
    - Create parent directories when requested by the output contract.
    - Record local paths, sizes, formats, and checksums when available.
    - Avoid overwriting existing files unless explicitly requested.
    - Report partial downloads and retain enough state for retry.

7. Persist sanitized history.
    - Store the generation request, selected model, provider, and statuses.
    - Store sanitized input and output artifact metadata.
    - Redact credentials, authorization headers, signed URLs, and secrets.
    - Support history lookup by local generation ID and basic filters.
    - Make history sufficient to resume jobs and locate downloaded files.
    - Define retention and cleanup behavior for stale jobs and artifacts.

### Resume video

Submit no-wait, exit, then use the local generation ID in a later
invocation to inspect/wait/download without manually supplying the
provider job ID.

### Diagnose

Use `pixgen info` for passive paths/runtime/provider state and
`pixgen doctor` for active core/plugin/provider checks.

### Add provider

Install a provider Python package into the PixGen tool environment.
Entry-point discovery registers the provider, optional provider-scoped
commands, and doctor checks without core edits.

## Success criteria

- Claude Code can discover models and create a local image/video using
    the Skill without provider-specific instructions embedded in it.
- Generic generation works against at least two independently
    authenticated providers.
- All four built-ins pass shared adapter contract tests; live tests
    are opt-in.
- An async job survives process exit and resumes from its local ID.
- No PixGen-controlled persisted/output data contains plaintext API
    keys.
- A separately installed fixture provider registers through the public
    plugin API.

## Constraints

- Local single-user execution.
- CPython 3.12+.
- Apache-2.0.
- Provider policies/availability are external constraints.
- Model catalogs are high-drift integration data.
- Public plugin API must remain smaller than internal APIs.

## Risks and assumptions

The main technical risk is over-normalizing incompatible providers.
Normalize stable concepts and preserve provider-specific capabilities
through metadata/escape hatches.

The product stop condition is convergence on one aggregator. If
direct-provider switching has little real value, stop expanding adapters
and simplify around the dominant aggregator.
