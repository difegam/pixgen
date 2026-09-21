---
name: pixgen-design-review
description: "Use when explicitly invoked to plan, research, review, or revise Pixgen feature changes and architecture proposals."
---

# Pixgen Design Review

Use repository evidence before making Pixgen-specific recommendations. Keep the
small provider-neutral core intact, and add only the structure the requested
change needs.

## Start with evidence

Read the relevant `.knowledge` documents, affected code and tests, and recent
Git state. Report repository facts, external facts, and inferences separately.
Do not claim that a proposal or pattern already exists without checking it.

Research only facts that may change, such as provider APIs, model capabilities,
SDK behavior, limits, or endpoint compatibility. Prefer official provider
documentation and cite it in a proposal. Do not browse for repository-only
design questions.

## Apply Pixgen boundaries

- Keep CLI and core request types provider-neutral. Adapters own wire formats,
  provider-native parameters, model quirks, and credential details.
- Add an abstraction only when two real implementations need the same stable
  boundary. Prefer a focused module over a generic factory, plugin system, or
  routing layer.
- Treat model manifests as the source of truth for capabilities, media limits,
  and evidence dates. An OpenAI-style base URL does not prove image or video
  compatibility.
- Inspect local media in explicit I/O work after model selection. Do not put
  provider policy in Pydantic field validators or silently transform media.
- Keep credentials, headers, raw provider payloads, and signed URLs out of
  configuration, persistence, logs, and normal output.
- Do not add automatic routing, fallback, live model discovery, or retries of
  ambiguous paid submissions without explicit user approval and documented
  behavior.

## Shape the decision

State the user-visible outcome, constraints, and any question that changes
scope. For a real architecture choice, present credible alternatives with their
trade-offs and recommend one. If the evidence supports one clear path, state it
directly instead of inventing options.

Classify the change with `superpowers:brainstorming`. Follow its approval gate
before changing code or a proposal. Update the existing source-of-truth proposal
when it covers the decision. Create a new document only for a separate lasting
decision.

When implementation is approved, use the relevant existing process skill:
`superpowers:writing-plans` for multi-step work,
`superpowers:test-driven-development` for code changes,
`superpowers:systematic-debugging` for unexpected behavior, and
`superpowers:verification-before-completion` before claiming success.
