# Pixgen design review skill design

Status: approved for skill authoring on 2026-09-21.

## Purpose

Create an explicit-only repository skill for Pixgen feature requests and design
proposal changes. The skill helps an agent investigate the relevant repository
evidence, research changing external facts when needed, present alternatives,
and preserve Pixgen's small provider-neutral design.

The skill does not replace the general brainstorming, planning, test-driven
development, debugging, or verification skills. It adds Pixgen-specific
decision rules before those workflows begin.

## Location and invocation

The skill lives at:

```text
.agents/skills/pixgen-design-review/
├── SKILL.md
└── agents/openai.yaml
```

Its name is `pixgen-design-review`. Its invocation policy disables implicit
selection. A user invokes it as `$pixgen-design-review` when they want this
process.

## Workflow

1. Identify whether the request changes a feature, an existing proposal, or an
   architecture boundary.
2. Read the relevant `.knowledge` source-of-truth documents, affected code and
   tests, and recent Git state. Do not claim a repository-specific conclusion
   before this inspection.
3. Research only facts that may have changed, such as provider APIs, models,
   limits, SDK behavior, or endpoint compatibility. Prefer official provider
   documentation. Label repository facts, external facts, and inferences
   separately.
4. State the user-visible outcome, constraints, and open questions. Ask one
   focused question when an unanswered choice changes scope or behavior.
5. For a genuine architecture choice, describe credible alternatives with their
   trade-offs and recommend one. Do not invent options when the evidence gives
   one clear path.
6. Classify scope and use the matching general workflow. Bounded code changes
   need a short approved design. Architectural work needs the full
   `superpowers:brainstorming` process and its written-spec gate.
7. Before implementation, preserve the established Pixgen principles and use
   the relevant planning, test-driven-development, debugging, and verification
   workflows.

## Pixgen decision rules

- Keep CLI and core request types provider-neutral. Provider adapters own wire
  formats, provider-native parameters, model quirks, and credential details.
- Add a new abstraction only when two real implementations need the same
  stable boundary. Prefer a focused module over a framework, generic factory,
  plugin system, or routing layer.
- Model manifests declare capabilities, media constraints, limits, and evidence
  dates. A matching OpenAI-style base URL alone does not prove image or video
  compatibility.
- Inspect local media in explicit I/O work after model selection. Do not put
  provider policy into Pydantic field validators or silently transform media.
- Keep credential data, headers, raw provider payloads, and signed URLs out of
  configuration, persistence, logs, and normal output.
- Do not add automatic routing, fallback, live model discovery, or retries of
  ambiguous paid submissions without explicit user approval and documented
  behavior.
- Update the existing source-of-truth proposal when it covers the decision. Add
  a new document only for a separate lasting decision.

## Authoring and validation

The authoring pass creates a concise `SKILL.md` and only the UI metadata needed
to make it explicit-only. It has no scripts or supporting references.

Baseline pressure scenarios already revealed two failure modes to address:

- A request for shared media resizing prompted a shared transformation subsystem
  before model constraints or user intent were inspected.
- A request for an OpenAI-compatible router prompted fallback behavior despite
  Pixgen's explicit-model and no-surprise-spending principles.

The skill must direct the agent to inspect first, distinguish a proposed feature
from an approved principle, and obtain explicit approval before adding hidden
media conversion or routing behavior.

After writing the skill, repeat those pressure scenarios with the skill loaded.
The expected result is an evidence-backed recommendation that rejects automatic
transformation and fallback by default while still offering a scoped option if
the user explicitly requests it.
