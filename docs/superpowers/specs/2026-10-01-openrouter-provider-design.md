# OpenRouter Image Provider Design

## Context

Pixgen currently supports image generation through direct OpenAI and Gemini
adapters. OpenRouter offers a unified Image API at `POST /api/v1/images` that
accepts an upstream image model slug, prompt, optional reference images, and
model-supported parameters. Its buffered response returns generated image
bytes as base64 plus an optional media type.

Pixgen's existing provider contract generates one `ProviderImage` for each
planned job. Its registry owns curated model definitions, the runtime creates
providers lazily, and provider credentials are read from environment variables.

## Goals

- Add OpenRouter as a provider using its dedicated Images API.
- Curate these OpenRouter models:
  - `google/gemini-3.1-flash-image`
  - `meta/muse-image`
  - `openai/gpt-image-2.5-sunburst`
- Preserve OpenRouter's native model slugs in Pixgen model IDs.
- Support image editing only for models whose OpenRouter Images API capability
  records document reference-image input.
- Reuse small, stable HTTP helpers without introducing a provider framework.
- Keep model listing and other catalogue-only commands usable without keys.

## Non-goals

- Use the `openrouter:image_generation` chat server tool. It adds an LLM that
  decides whether to invoke image generation, which does not match Pixgen's
  deterministic model selection and one-image-per-job contract.
- Dynamically discover and register every model available through OpenRouter.
- Add provider routing controls, attribution headers, streaming, multi-image
  `n` batching, or provider-specific passthrough options in this change.
- Change the configured default create or edit models.
- Add an OpenRouter SDK or another runtime dependency.

## Model Identity and Catalogue

Pixgen IDs will use the provider adapter as the first segment and preserve the
upstream model slug in the remainder:

| Pixgen ID | OpenRouter request model |
| --- | --- |
| `openrouter/google/gemini-3.1-flash-image` | `google/gemini-3.1-flash-image` |
| `openrouter/meta/muse-image` | `meta/muse-image` |
| `openrouter/openai/gpt-image-2.5-sunburst` | `openai/gpt-image-2.5-sunburst` |

OpenRouter's image API uses author/model slugs, and common model integrations
keep the OpenRouter connection separate from that slug. Pixgen will follow the
same distinction with `openrouter/<author>/<slug>` IDs.

`ModelId` validation will be adjusted to allow one provider segment followed by
one or more non-empty model path segments. The provider remains the first
segment; `ModelSpec.model` remains the full remainder. This permits exact
upstream slugs without a lossy translation map. Malformed IDs with empty path
segments, uppercase characters, or invalid characters remain rejected.

All three models support image creation. Gemini 3.1 Flash Image supports edits
with up to 14 references, and GPT Image 2.5 Sunburst supports edits with up to
16 references. Muse Image is create-only in the initial catalogue: although its
model page describes editing, the current OpenRouter Images API model record
does not advertise `input_references`. Pixgen will not send edit requests to
that endpoint for Muse until the capability is documented there.

Catalogue parameter schemas will follow OpenRouter's current per-model
capability records:

- Gemini: `aspect_ratio` and `resolution` (`512`, `1K`, `2K`, or `4K`). Its
  supported aspect ratios are `1:1`, `1:4`, `1:8`, `2:3`, `3:2`, `3:4`,
  `4:1`, `4:3`, `4:5`, `5:4`, `8:1`, `9:16`, `16:9`, and `21:9`.
- GPT Image 2.5 Sunburst: `aspect_ratio`, `quality` (`auto`, `low`, `medium`,
  `high`, `xhigh`, `max`), `background` (`auto`, `transparent`, `opaque`), and
  `output_compression` (0–100). Its supported aspect ratios are `1:1`, `3:2`,
  `2:3`, `4:3`, `3:4`, `16:9`, `9:16`, and `21:9`.
- Muse Image: no provider-native parameters until the Images API publishes
  supported parameters for it.

Shared aspect-ratio selection will be available only where the catalogue
definition declares a corresponding supported ratio. Model schemas and ratios
will be reviewed when OpenRouter's capabilities change; this release does not
query the live catalogue at runtime.

## Request and Response Flow

`OpenRouterProvider.generate` will use the existing `PreparedImageRequest` and
`ProviderImage` boundary:

1. Read the canonical Pixgen model ID and use the full model portion after the
   first slash as OpenRouter's `model` value.
2. Build a JSON payload with that model, the prompt, and non-null validated
   model parameters.
3. When references are present, encode each local image as a base64 data URL
   and send it in OpenRouter's `input_references` image URL structure.
4. POST to `/api/v1/images` with bearer authentication and the configured
   request timeout.
5. Validate the response, decode the first returned `b64_json` image, and use
   its `media_type`. If the API omits the media type, use `image/png`.

Pixgen's `--variants` behavior remains a set of separate provider calls. The
OpenRouter API supports `n` for some models (up to 10 for GPT Image 2.5
Sunburst), while Gemini currently caps it at one and Muse has no documented
`n` support. Batching only selected models would create different failure and
result semantics; it is not part of this integration.

## Runtime, Credentials, and CLI

`Settings` will add an OpenRouter secret using environment aliases
`OPENROUTER_API_KEY` and `PIXGEN_OPENROUTER_API_KEY`. Provider keys remain
environment-only and will not be added to TOML configuration or logs.

The runtime will create an OpenRouter HTTP client factory only when a key is
configured. As with current providers, the client is instantiated lazily when
generation first needs it. OpenRouter will be added to the registry and the
provider CLI factory list, exposing the existing create/edit command patterns
for the operations each catalogue model supports. Registry validation will
reject an edit for Muse before making a paid request.

## Reuse Boundaries

Use the existing `httpx2.AsyncClient`; do not add an SDK or create a generic
provider superclass. Extract only small helpers that have at least two real
consumers:

- A client-factory helper parameterised by API key, base URL, and timeout, used
  by OpenAI and OpenRouter.
- A validated base64 image decoder used by both HTTP adapters, with
  provider-specific error messages supplied by their response parsers.

Keep payload building, API response-envelope validation, HTTP error mapping,
and provider catalogues in their respective adapters. Gemini uses a different
SDK and remains outside these HTTP helpers. Avoid generalising error handling
until the provider-specific mappings demonstrate a stable shared contract.

## Errors

Map transport and HTTP failures to existing Pixgen error codes:

- Missing key: `credential_unavailable`.
- HTTP 401/403: `authentication_failed`.
- HTTP 404: `model_not_found`.
- HTTP 429: `rate_limited`.
- Timeout: `timeout`.
- Connection and server errors: `provider_unavailable`.
- Other HTTP 4xx errors: `invalid_request`, except recognised moderation or
  content-policy failures, which map to `content_rejected`.
- Invalid, empty, or undecodable image response: `provider_failure`.

Error messages must be safe and concise; do not include credentials, base64
image data, or raw provider response bodies.

## Verification and Documentation

Tests will cover:

- Nested `ModelId` acceptance and malformed nested path rejection.
- Catalogue IDs, operations, parameters, reference limits, and aspect ratios.
- Create and edit request payloads, including exact upstream model slugs and
  base64 data URLs.
- Response media-type handling, base64 validation, and malformed or empty
  responses.
- Timeout, connection, authentication, not-found, rate-limit, invalid-request,
  content-rejection, and server-error mappings.
- Runtime lazy client creation, provider availability, and CLI factory
  registration without making network calls.
- Separate-call variant behavior and rejection of Muse edits before provider
  invocation.

README configuration and usage examples will document the OpenRouter key,
nested model IDs, and provider-native commands. `pixgen.toml` defaults remain
unchanged. No live provider credentials or network calls are required for the
test suite.

## Sources

- [OpenRouter Image Generation API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [OpenRouter current Image Models API](https://openrouter.ai/api/v1/images/models)
- [OpenRouter Image Generation Server Tool](https://openrouter.ai/docs/guides/features/server-tools/image-generation)
- [OpenRouter Muse Image model page](https://openrouter.ai/meta/muse-image)
- [OpenRouter GPT Image 2.5 Sunburst model page](https://openrouter.ai/openai/gpt-image-2.5-sunburst/)
- [Pydantic AI OpenRouter model naming](https://pydantic.dev/docs/ai/models/openrouter/)
- [LangChain OpenRouter integration](https://docs.langchain.com/oss/python/integrations/chat/openrouter)
