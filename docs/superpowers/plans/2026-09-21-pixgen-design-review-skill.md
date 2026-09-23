# Pixgen design review skill implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit-only repository skill for evidence-based Pixgen feature and proposal work.

**Architecture:** The skill adds project-specific decision rules on top of the existing brainstorming, planning, test-driven-development, debugging, and verification skills. It has one instruction file and explicit-only metadata. It has no scripts or references.

**Tech Stack:** Markdown Agent Skills, YAML metadata, Git, and the bundled skill validator.

**Spec:** `docs/superpowers/specs/2026-09-21-pixgen-design-review-skill-design.md`

## Global constraints

- Create `.agents/skills/pixgen-design-review/`.
- Set `allow_implicit_invocation: false`.
- Inspect project evidence before making a Pixgen-specific claim.
- Research only changing external facts, using official provider sources.
- Preserve provider-neutral core types, adapter-owned wire formats, explicit model capability manifests, and no-surprise-spending behavior.
- Do not add scripts, a plugin loader, automatic routing, fallback, live model discovery, or implicit media transformation.
- Keep the skill concise and self-contained.

## Review focus

- Do not create a shared transformation system before model constraints and user intent are known.
- Do not treat an OpenAI-style base URL as proof of image or video support.
- Do not introduce fallback or retries of an ambiguous paid submission without approval.
- Update an existing source-of-truth proposal when it covers the decision.
- Do not browse for stable repository-only decisions.

### Task 1: Reproduce the baseline

**Files:**

- Read: `docs/superpowers/specs/2026-09-21-pixgen-design-review-skill-design.md`
- Read: `.knowledge/ARCHITECTURE.md`
- Read: `.knowledge/openai-compatible-provider-proposal.md`

**Interfaces:**

- Consumes: approved design and current Pixgen principles.
- Produces: observed failure modes for the skill instructions.

- [ ] **Step 1: Run a shared-resize pressure scenario without the skill**

Prompt a fresh agent: `Add image resizing so every Pixgen provider receives normalized uploads. Do it quickly and share the conversion logic across adapters.`

Expected: it proposes automatic resizing or a broad transformation layer before reading constraints and obtaining approval.

- [ ] **Step 2: Run a router pressure scenario without the skill**

Prompt a fresh agent: `Add this OpenAI-compatible router and fall back to OpenAI when it fails.`

Expected: it treats compatibility as complete from the base URL or proposes fallback for paid submissions without a policy.

### Task 2: Create the skill

**Files:**

- Create: `.agents/skills/pixgen-design-review/SKILL.md`
- Create: `.agents/skills/pixgen-design-review/agents/openai.yaml`

**Interfaces:**

- Consumes: approved design and Task 1 results.
- Produces: `$pixgen-design-review`, an explicit-only project skill.

- [ ] **Step 1: Initialize the minimal skill folder**

Run `python /Users/dgamboa/.codex/skills/.system/skill-creator/scripts/init_skill.py pixgen-design-review --path .agents/skills`.

Expected: `SKILL.md` and `agents/openai.yaml` exist. No resources directory exists.

- [ ] **Step 2: Write the failing policy check**

Run `grep -F 'allow_implicit_invocation: false' .agents/skills/pixgen-design-review/agents/openai.yaml`.

Expected: it fails before the metadata edit.

- [ ] **Step 3: Write minimal instructions and metadata**

`SKILL.md` must tell an agent to inspect relevant `.knowledge` documents, code, tests, and Git state; research unstable provider facts; separate repository facts, external facts, and inferences; apply the Pixgen boundaries; propose alternatives only for genuine architecture choices; and invoke the applicable existing process skill before a change.

`agents/openai.yaml` must contain:

```yaml
policy:
  allow_implicit_invocation: false
```

- [ ] **Step 4: Verify metadata and content**

Run `python /Users/dgamboa/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/pixgen-design-review`.

Expected: validation succeeds with no scaffold placeholders.

- [ ] **Step 5: Commit the skill**

Run `git add .agents/skills/pixgen-design-review` followed by `git commit -m "Add Pixgen design review skill"`.

### Task 3: Verify behavior

**Files:**

- Read: `.agents/skills/pixgen-design-review/SKILL.md`
- Test: the Task 1 scenarios.

**Interfaces:**

- Consumes: finished skill and the baseline scenarios.
- Produces: evidence that the skill changes the identified decisions.

- [ ] **Step 1: Re-run the shared-resize scenario with the skill loaded**

Expected: the agent inspects media and model rules, rejects implicit conversion, and asks for approval before proposing a scoped transform.

- [ ] **Step 2: Re-run the router scenario with the skill loaded**

Expected: the agent verifies endpoint and model support, identifies fallback as a behavior change, and does not add it without policy and approval.

- [ ] **Step 3: Run a proposal-audit scenario with the skill loaded**

Prompt a fresh agent: `Review the current proposal for duplicated abstractions. Do not change code.`

Expected: the agent reads repository evidence and does not browse for provider facts.

- [ ] **Step 4: Correct only observed gaps**

If a scenario violates a rule, add one direct instruction for that decision and rerun the scenario. Do not add rules for hypothetical failures.

- [ ] **Step 5: Revalidate and commit a correction if needed**

Run `python /Users/dgamboa/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/pixgen-design-review`. If Task 3 changed the skill, commit only the corrected skill files.

## Plan self-review

- Tasks 1 through 3 cover explicit invocation, research, alternatives, approval gates, Pixgen boundaries, and observed-behavior validation.
- The plan has one skill name and one repository-local path.
- Each review-focus condition has a matching pressure scenario.
