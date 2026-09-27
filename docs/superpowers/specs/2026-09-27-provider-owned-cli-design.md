# Provider-owned image parameters and CLI

**Status:** Written spec awaiting user review

**Date:** 2026-09-27

## Intent and agreed scope

Replace the string-based `--param` interface with provider-owned Pydantic parameter models and Cyclopts sub-apps. Compose model identity, restrictions, and parameter definitions in one provider-owned model definition. The main CLI and application must not contain model-specific parameter branches.

Keep `pixgen image <operation>` for shared multi-model invocations. These use provider/model defaults plus one optional shared generation parameter, `aspect_ratio`. Provider subcommands expose the full native parameter set. All selected models must accept an explicitly supplied shared ratio before generation starts.

Adding a model changes only its provider package and its tests. Adding a provider requires its package, tests, and composition-root registration, with credential configuration where needed. It requires no changes to the main CLI's command logic. This remains an internal provider contract, not a third-party plugin system.

The approved scope includes removing `--param`, preserving existing orchestration and output behaviour, extending model introspection, and documenting replacement commands. It does not add new providers, new generation parameters, image conversion, or the separately designed media commands.

## Existing code and boundaries

The current `cli/image.py` defines shared create/edit commands and passes raw parameter strings into `ImageApplication.run`. `core/params.py` parses those strings. Provider modules already own native Pydantic models, but their model catalogues and parameter-model selection are separate. Validated requests currently reduce parameters to JSON dictionaries.

The refactor joins these definitions, removes CLI syntax handling from the application, and carries concrete validated parameter models to provider adapters. Existing local changes in this checkout are the baseline and must be preserved, including lazy client construction and current error/output handling.

The architectural boundaries remain:

- `core/`: pure data models, restrictions, and shared parameter validation. No Cyclopts, clients, filesystem access, or provider imports.
- `cli/`: generic command assembly, shared options, invocation, and rendering. No imports of concrete provider packages.
- `providers/`: native parameter models, model definitions, mappings, adapters, and provider CLI factories.
- `application.py`: model resolution, preflight, input loading, concurrency, variants, and results.
- `runtime.py`: composition and dependency injection.

Provider packages may be split into focused modules for parameters, definitions, adapter, and CLI. The provider adapter must remain usable without constructing its CLI. CLI construction must not create network clients.

## Command structure

Shared commands retain their operation-first layout:

```bash
pixgen image create "A forest" \
  --model openai/gpt-image-2 \
  --model gemini/gemini-3.1-flash-image \
  --aspect-ratio 16:9

pixgen image edit "Add morning mist" \
  --image forest.png \
  --model openai/gpt-image-2 \
  --aspect-ratio 3:2
```

Provider sub-apps are mounted beneath each supported operation:

```bash
pixgen image create openai "A forest" \
  --model gpt-image-2 --quality high --size 1536x1024

pixgen image create gemini "A forest" \
  --model gemini-3.1-flash-image --image-size 2K --aspect-ratio 16:9
```

Shared commands accept repeated canonical `provider/model` IDs and retain the configured default model lists when omitted. Native commands target one model, require `--model`, and accept the provider-local model name shown above. Native model selection is restricted to that provider. Shared commands remain available for selecting multiple models from the same provider.

Keep common input and execution flags, including references/images, variants, output paths, directory creation, overwrite behaviour, timeout, and JSON rendering. Reusable option models and generic command helpers supply these to provider commands. Providers define native flags through their own Pydantic models; they do not duplicate execution or rendering logic.

`--param` is removed from both CLI and application interfaces. There is no generic native-parameter escape hatch in shared commands. Unsupported flags produce normal CLI errors.

### Dispatch verification

A throwaway probe against installed Cyclopts 4.25.2 verified that an operation app can have both a shared default command and provider sub-apps. Ordinary positional prompts dispatch to the shared command. An exact provider-name token dispatches to that sub-app, even when quoted by the shell.

Both forms below disambiguate a shared prompt matching a provider name:

```bash
pixgen image create --prompt "openai"
pixgen image create --model openai/gpt-image-2 -- "openai"
```

Document `--prompt` as the straightforward disambiguation. Add regression tests for this behaviour rather than implementing a custom command parser.

## Shared aspect-ratio model

`SharedImageParams` is a frozen Pydantic model with forbidden extra fields and one optional field, `aspect_ratio`. Absence means preserve provider/model defaults. Do not assign an implicit square ratio or expose a separate `auto` value.

The ratio accepts the textual form `width:height`, with two positive decimal integers. Reject zero, negative numbers, decimals, missing components, and alternative separators. Canonicalise by greatest common divisor: `32:18` becomes `16:9`, and `2:2` becomes `1:1`. Expose canonical strings in errors, mappings, schemas/examples, and results wherever the ratio is represented.

The shared type validates syntax independently of model support. A syntactically valid ratio such as `7:5` is rejected for a selected model unless its definition has an explicit mapping. There is no global enum that must be updated whenever a provider supports a new ratio.

### Predefined conversion maps

Every model/operation definition owns a mapping from canonical ratios to native parameter overrides. Maps may be reused across models when their restrictions match. Runtime conversion is a lookup followed by native Pydantic validation. It does not calculate a nearest size or infer support from a provider name.

Initial OpenAI mappings are:

| Ratio | GPT Image 2 size | GPT Image 1 Mini size |
|---|---|---|
| `1:1` | `1024x1024` | `1024x1024` |
| `2:3` | `1024x1536` | `1024x1536` |
| `3:2` | `1536x1024` | `1536x1024` |
| `3:4` | `864x1152` | Unsupported |
| `4:3` | `1152x864` | Unsupported |
| `9:16` | `864x1536` | Unsupported |
| `16:9` | `1536x864` | Unsupported |
| `7:3` (input `21:9`) | `1792x768` | Unsupported |

These are Pixgen's deliberate default-size choices for a supplied ratio. They do not promise equal resolution or generation cost across providers. GPT Image 2 mappings must satisfy its documented dimension restrictions; GPT Image 1 Mini retains its supported presets.

For the currently registered Gemini models, map canonical values `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `9:16`, and `16:9` directly to the native `aspect_ratio` field. Map canonical `7:3` to the provider's native spelling `21:9`. Leave `image_size` unset to preserve model defaults. Do not expand the native catalogue solely because research found newer API capabilities.

Apply these mappings to the currently supported create and edit operations. Future operation-specific restrictions may supply different maps.

Strictness means the provider supports the requested named ratio and Pixgen does not substitute another. It does not promise an exact mathematical ratio in returned pixels: some documented native presets use rounded dimensions. Do not crop, resize, or retry with another ratio to conceal that difference.

## Composed definitions and executable contracts

Use a frozen generic Pydantic `ModelDefinition[Params]` to associate existing catalogue metadata with operation definitions. Each operation definition contains its concrete native parameter type, validated provider defaults, input restrictions, and shared-ratio conversion map. Retain the existing public model metadata as a serialisable projection rather than serialising Python classes.

Native parameter models use frozen Pydantic models with forbidden extras. Provider-local inheritance/composition may share fields across related models. Concrete model/operation definitions remain authoritative for restrictions. Avoid a central union listing every provider's parameter model.

Keep a separate executable Python protocol for providers and a CLI-factory contract. Pydantic models do not contain Cyclopts apps, network clients, or orchestration callbacks.

The provider contract must support:

- Enumerating model definitions and resolving a known model/operation without fallback to an unrelated schema.
- Preparing native parameters from defaults and optional shared parameters.
- Validating native requests against the selected model and operation.
- Reporting output media type and generating through the existing prepared-media path.

The CLI factory receives a narrow shared invocation service and returns an operation-specific Cyclopts app named after the provider. The composition root supplies these factories to generic CLI assembly. Providers retain ownership of their app, native flag definitions, and model-specific validation; the common invocation service handles execution and rendering.

Registration rejects duplicate provider command names, duplicate canonical model IDs, mismatched model ownership, and CLI operation declarations that disagree with definitions. Contract tests validate mapping entries against concrete native schemas. Structural typing alone is not treated as proof of behavioural compatibility.

Cyclopts may expose a provider's common native parameter model while model-specific validation enforces narrower restrictions. Help must direct users to `model get` for those restrictions. Introducing a model with new native fields may update that provider's CLI, but never the main CLI.

## Typed requests and data flow

Intents hold prompt, operation, and media paths. Remove the untyped generation-parameter bag from intents. Shared calls supply `SharedImageParams`; native calls supply the provider's concrete parameter model. Both produce model-specific validated requests with typed native parameters.

Use concretely parameterised request models at provider boundaries so validation and serialisation retain all native fields. Shared orchestration treats parameters as opaque validated data. Provider adapters perform final API-specific serialisation; Pydantic aliases handle equivalent names, while ratio lookup handles actual conversion.

The shared invocation sequence is:

1. Parse shared options and canonicalise the ratio.
2. Resolve selected models, operations, availability, and job limits.
3. For every target, load its defaults, apply its predefined ratio override if supplied, and validate the resulting native model and input restrictions.
4. Complete local media and output preflight before generation. Parameter incompatibility must not start a generation request or create output artifacts.
5. Execute the existing jobs with concurrency, timeout, variants, error handling, and atomic writes.

Local input loading may occur as needed for media checks, but all targets must pass preflight before any generation/client network work. Preserve lazy client construction.

Native commands enter the same preflight/execution pipeline with their selected model and native parameters. They cannot bypass model restrictions by providing a broadly typed provider parameter instance.

The first incompatible target may fail the invocation using the existing invalid-request result and exit code 2. Its message identifies the model, operation, rejected ratio, and supported ratios. Strict preflight does not change runtime failure semantics: once execution begins, existing partial-success results remain possible.

## Defaults and introspection

Provider-owned parameter defaults and API defaults remain in effect for omitted fields. A shared ratio overrides only the native fields named by its mapping. Do not send absent values as explicit nulls or introduce common quality/resolution defaults.

`pixgen model list` remains an offline catalogue command. `pixgen model get` includes native JSON parameter schemas and canonical supported shared ratios per operation. Public JSON must contain no Python type objects or clients. Existing public model metadata is preserved; supported shared ratios are an additive introspection field.

The main CLI's shared help explains the ratio syntax and strict compatibility. Provider help exposes native options. Neither help nor catalogue commands require credentials or client construction.

## Verification and acceptance criteria

Use the repository's behaviour-first TDD workflow during implementation. Required coverage includes:

- Valid and invalid ratio syntax, equivalent-ratio normalisation, and omission preserving defaults.
- Every initial predefined mapping, native validation of mapped values, and absence of fallback for unsupported values.
- A compatible multi-model request and an incompatible later target proving zero generation calls and no artifacts.
- Both operations, provider-specific restrictions, native flag parsing, and refusal of removed `--param`.
- Shared/native dispatch, provider-name prompt disambiguation, and help/catalogue use without credentials or clients.
- Concrete typed parameter fields surviving validation and serialisation into native payloads.
- Duplicate registrations and disagreement between definitions and CLI operation support.
- A fake additional provider and model registered through the public internal contract without editing main CLI code.
- Existing variants, timeouts, output planning, atomic writes, result rendering, and partial-failure behaviour remaining covered.

Implementation completion requires `just lint && just type-check && just test`. No real API requests, credentials, or user files are used in tests. This spec-only change does not claim implementation or test-suite completion.

Update the README with shared and native command examples, the breaking removal of `--param`, model-specific ratio support, defaults, and prompt disambiguation. Preserve unrelated working-tree changes.

## Research supporting the design

- [Cyclopts structured classes](https://github.com/brianpugh/cyclopts/blob/main/docs/source/user_classes.rst) and [command composition](https://github.com/brianpugh/cyclopts/blob/main/docs/source/commands.rst) support the intended typed options and app assembly. Local dispatch was verified with version 4.25.2.
- [Pydantic aliases](https://github.com/pydantic/pydantic/blob/main/docs/concepts/alias.md) rename fields; [generic models](https://github.com/pydantic/pydantic/blob/main/docs/concepts/models.md) require concrete parameterisation to preserve intended validation and serialisation.
- [OpenAI image generation](https://developers.openai.com/api/docs/guides/image-generation) documents model-specific sizes and restrictions. [Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation) documents native ratio presets and their rounded output dimensions.
- [FLUX.2](https://docs.bfl.ai/api-reference/models/generate-or-edit-an-image-with-flux2-%5Bpro%5D), [Stability](https://platform.stability.ai/docs/api-reference), [Ideogram](https://developer.ideogram.ai/api-reference/generate-images/generate-v3), and [Nova Canvas](https://docs.aws.amazon.com/nova/latest/userguide/image-gen-req-resp-structure.html) demonstrate why future geometry support needs provider-owned conversion and operation-specific restrictions.

The research informed the contract; it does not authorise adding these providers or expanding the shared parameter set. Output format, seeds, negative prompts, quality, resolution, and other generation controls remain outside the shared model.
