# Create model groups

**Status:** Design ready for review  
**Date:** 2026-10-01  
**Scope:** Named, create-only model selections loaded from Pixgen TOML configuration

## Summary

Pixgen will support named model groups in `pixgen.toml`. A group is a reusable
collection of models with presentation metadata, selected with `pixgen create
--group NAME`.

```toml
[groups.product-hero]
description = "Models suited to product hero images"
tags = ["product", "marketing"]
models = [
  "openai/gpt-image-2",
  "gemini/gemini-3.1-flash-image",
]
```

The first release treats a group as a CLI convenience for selecting models.
`description` and `tags` are stored for a future `group list`/`group show`
presentation but do not affect generation, output names, or result metadata.

## Goals

- Allow users to select several create models with one stable group name.
- Keep group definitions in the existing Pixgen TOML configuration flow.
- Preserve model ordering from the configuration in generation planning.
- Validate group structure before a command can use it.
- Keep model/provider validation in the existing application and registry flow.
- Make the configuration model reusable by future group presentation commands.
- Make `--group` and `--model` mutually exclusive.
- Remove the shared root `create --aspect-ratio` option from this workflow.

## Non-goals

The first release does not:

- support groups for `edit`;
- define aspect ratios, prompts, references, or provider-specific parameters in groups;
- change provider-native commands or their provider-specific aspect-ratio options;
- add a `group list` or `group show` command;
- attach descriptions or tags to generated artifacts or `CommandResult`;
- make groups recursive, inherited, or dynamically composed;
- replace the existing `defaults.image_create_models` fallback;
- add a new provider/plugin abstraction.

## User-facing command behavior

### Create with a group

```text
pixgen create --group product-hero "A modern running shoe on a studio set"
```

The command resolves `product-hero` to its configured model tuple and passes
that tuple through the existing shared model-selection path. Generation then
uses the existing provider availability, model support, media, concurrency,
variant, output, and artifact validation.

### Selection precedence and exclusions

- `pixgen create --group NAME` selects the group models.
- `pixgen create --model MODEL ...` keeps the existing explicit selection.
- `pixgen create` with neither option keeps using
  `defaults.image_create_models`.
- `--group` and `--model` are mutually exclusive and are rejected by CLI
  parsing when supplied together.
- `--group` is not registered on `edit`.
- The shared root `create --aspect-ratio` option is removed. Provider-native
  commands keep their existing native options and internal parameter support.

An unknown group is a command-level `invalid_request` error. It is rendered by
the existing human/JSON error path and does not call the application or a
provider.

## Configuration model

`Settings` gains a `groups` mapping. Each value is a frozen Pydantic model:

```python
class ModelGroup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    models: tuple[ModelId, ...] = Field(min_length=1)
    description: str = Field(min_length=1)
    tags: tuple[str, ...] = ()
```

The group name is the exact TOML table key. Names must be non-empty; they are
not normalised or aliased. Models preserve TOML order. Group validation also
rejects duplicate model IDs, blank descriptions, blank tags, and tags with
leading or trailing whitespace. Unknown fields in a group are rejected.

Model IDs are validated for the existing canonical provider/model syntax when
settings load. Whether a validly-shaped model is present in the runtime
provider registry remains an application concern, consistent with the current
`defaults.image_create_models` behavior.

An omitted `groups` table produces an empty mapping. Existing configuration
without groups remains valid.

## Architecture

Groups remain a configuration and CLI concern. They do not become a new core
selection type in the first release.

```text
pixgen.toml
    -> Settings.groups
    -> CLI create --group resolver
    -> SharedSelection(models=group.models)
    -> ImageApplication.run()
    -> existing registry/provider flow
```

Expected responsibilities:

- `config.models` owns `ModelGroup` and TOML validation.
- `cli.app` passes configured groups while building the root command tree.
- `cli.image` registers the create-only option, enforces mutual exclusion, and
  resolves the selected name.
- `core.requests.SharedSelection` remains the execution boundary for the
  resolved model tuple.
- `application.ImageApplication` remains responsible for runtime model and
  provider validation; it does not need group-specific logic.
- Future group presentation commands will read `Settings.groups` directly.

The likely implementation surface is limited to:

- `src/pixgen/config/models.py`;
- `src/pixgen/cli/app.py`;
- `src/pixgen/cli/image.py`;
- configuration and CLI tests;
- the example `pixgen.toml` and user documentation.

No application, provider, artifact, or result-model changes are required.

## Error handling and compatibility

Configuration errors are reported as `invalid_configuration` through the
existing runtime startup path. These include malformed TOML, invalid model
IDs, duplicate models, blank metadata, and unknown group fields.

Command errors use the existing `invalid_request` code for an unknown group.
The error includes the requested group name and does not reveal credentials or
provider secrets. A group containing a model that is not in the provider
registry follows the existing model-resolution error behavior after selection
is normalised.

The public `CommandResult` schema is unchanged. Group name, description, and
tags are intentionally absent from generation results in this release.

## Testing strategy

Configuration tests will cover:

- loading a valid `[groups.<name>]` table;
- preserving model order and tags;
- empty/default groups behavior;
- duplicate models;
- blank descriptions and tags;
- invalid model IDs;
- unknown group fields;
- compatibility with configuration that has no groups.

CLI tests will cover:

- parsing `create --group NAME`;
- resolving a group to the expected `SharedSelection.models`;
- rejecting `--group` together with repeated `--model`;
- rejecting `--group` on `edit`;
- rejecting the removed shared `--aspect-ratio` option;
- returning an `invalid_request` outcome for an unknown group;
- retaining create defaults and explicit model selection when no group is used.

The tests use in-memory settings, fakes, and parser invocation. They do not
make provider requests, require credentials, or access user files.

## Future extension

The group model deliberately stores presentation metadata now so a later
`group list`/`group show` command can expose the same configuration without
changing the TOML schema. That future command may add dedicated result models,
but this design does not reserve generation-result fields or introduce a
runtime group identity.
