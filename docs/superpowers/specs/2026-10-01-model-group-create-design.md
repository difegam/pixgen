# Create model groups from the CLI

**Status:** Approved design
**Date:** 2026-10-01
**Scope:** Create named model groups interactively or from repeated CLI options

## Summary

Pixgen will add a dedicated `group create` command for writing named model
groups to the existing TOML configuration file. The command supports explicit
model IDs for scripts and an interactive fuzzy-search selector for terminal
users.

```text
pixgen group create product-hero \
  --model openai/gpt-image-2 \
  --model gemini/gemini-3.1-flash-image \
  --description "Models for product hero images" \
  --tag product \
  --tag marketing
```

When `--model` is omitted from an interactive terminal, the command presents
the provider registry as a searchable multi-select list. The resulting group
contains only `models`, `description`, and `tags`. These fields are metadata
for future `group list` and `group show` commands; they do not affect image
generation or provider construction.

## Goals

- Provide a dedicated `pixgen group create NAME` command.
- Support repeated `--model MODEL` options for automation.
- Support interactive fuzzy search and multi-selection without adding a new
  runtime dependency.
- Validate every selected model against the curated provider registry.
- Create the parent configuration directory when needed and write the group
  atomically to the resolved Pixgen TOML file.
- Preserve all unrelated existing configuration sections and group ordering as
  far as the serializer permits.
- Keep group creation independent of credentials and network requests.
- Store only `models`, `description`, and `tags` in a group definition.

## Non-goals

The first release does not:

- change `create --group NAME` or `create --model MODEL` generation behavior;
- allow groups on `edit`;
- define aspect ratios, prompts, references, or provider-native parameters in
  groups;
- add `group list` or `group show` presentation commands;
- add a separate group-management dependency or external service;
- silently merge, replace, or mutate an existing group through `group create`;
- create or initialise provider API clients.

## User-facing behavior

### Explicit selection

```text
pixgen group create product-hero \
  --model openai/gpt-image-2 \
  --model gemini/gemini-3.1-flash-image \
  --description "Models for product hero images"
```

`--model` is repeatable and preserves command-line order. `--description` is
required for explicit creation because the current `ModelGroup` schema requires
non-blank presentation text. `--tag` is repeatable and optional.

### Interactive selection

```text
pixgen group create product-hero
```

Interactive mode is entered only when no models are supplied and the command
has an interactive terminal. The selector displays canonical model IDs,
supports case-insensitive fuzzy filtering, uses arrow keys to move, Space to
toggle selection, and Enter to confirm. It then prompts for the required
description and optional comma-separated tags unless those values were already
provided as options.

An empty selection is rejected. A non-interactive invocation without at least
one `--model` is rejected with an actionable error rather than attempting to
read stdin.

### Existing names

`group create` is create-only. If the requested name already exists, the
command returns an `invalid_request` error and leaves the file unchanged. A
future explicit `group edit` or `group add` command may handle modifications;
this release does not define those semantics.

### Configuration output

The group is written in the existing format:

```toml
[groups.product-hero]
description = "Models for product hero images"
tags = ["product", "marketing"]
models = [
  "openai/gpt-image-2",
  "gemini/gemini-3.1-flash-image",
]
```

The path comes from `PIXGEN_CONFIG` when set, otherwise from
`resolve_config_path()`. Missing parent directories are created. The writer
reads the current TOML, updates only the `groups` table, serialises the
supported settings deterministically, and publishes through a sibling
temporary file followed by an atomic rename. Invalid existing configuration
must fail before any write occurs.

The implementation must not write API keys or other secrets. It must preserve
existing `defaults` and `generation` values. Because the standard library can
parse TOML but does not provide a TOML writer, the serializer will be a small
internal writer for Pixgen's supported configuration shape rather than a new
dependency.

## Architecture

```text
CLI group create
    -> ProviderRegistry.models() for choices and validation
    -> ModelGroup metadata validation
    -> configuration repository / TOML serializer
    -> atomic file publication
    -> success result
```

Expected responsibilities:

- `cli.group` owns Cyclopts command registration, interactive prompts, fuzzy
  matching, and user-facing command errors.
- `ProviderRegistry` remains the source of curated model IDs and model specs.
- `config.models` remains the source of `ModelGroup` validation.
- A configuration write component owns read/modify/serialise/write behavior and
  must not be coupled to provider clients or image generation.
- `runtime.py` may construct a registry for this command, but group creation
  must not require credentials or instantiate active provider clients.
- Existing `cli.image` group resolution remains read-only and unchanged.

The selector should be isolated behind a small callable interface so tests can
exercise command behavior without terminal escape sequences. The fuzzy matcher
must be deterministic: exact prefix matches rank first, then ordered
case-insensitive substring matches, then remaining matches in registry order.

## Validation and errors

- Unknown model IDs return `model_not_found` or the existing registry error and
  do not write the file.
- Duplicate model IDs are rejected before writing.
- Blank or whitespace-padded descriptions and tags use existing Pydantic
  validation rules.
- Empty interactive selections are rejected.
- Existing group names return `invalid_request` without modifying the file.
- Malformed TOML or invalid existing settings return
  `invalid_configuration` without modifying the file.
- Filesystem failures use the existing Pixgen error path and include the
  resolved config path without exposing secrets.
- All validation happens before the temporary output is published.

## Testing strategy

Configuration repository tests will cover:

- creating a new file and parent directory;
- adding a group to an existing config while preserving defaults and
  generation settings;
- deterministic output for models, description, and tags;
- atomic-write failure behavior;
- duplicate existing names;
- malformed existing TOML;
- invalid models and metadata;
- `PIXGEN_CONFIG` path resolution;
- absence of credentials in written output.

CLI tests will cover:

- repeated explicit `--model` options and order preservation;
- required explicit description and optional repeated tags;
- interactive selector invocation with a fake selector;
- fuzzy ranking and selection confirmation;
- rejection of interactive mode on non-TTY input;
- unknown models and empty selections;
- existing group rejection;
- no provider client or image application invocation.

Tests will use temporary paths, fake registries/selectors, and in-memory
streams. They will not use credentials, user configuration, network access, or
real terminal control sequences.

## Future extension

The TOML schema intentionally matches the existing `ModelGroup` model so future
`group list`, `group show`, `group edit`, and `group add` commands can build on
the same repository without changing image-generation interfaces.
