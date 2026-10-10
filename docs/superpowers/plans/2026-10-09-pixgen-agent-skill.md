# Pixgen Agent Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one portable, installable Pixgen CLI Agent Skill that prefers native image generation when the active harness provides it, stays outside the Python package, and documents installation through `skills`.

**Architecture:** Keep a canonical skill in `skills/pixgen-cli/` with concise `SKILL.md` instructions and one directly linked CLI reference. Add README installation instructions, then verify Agent Skills metadata, named-skill discovery, and package exclusion.

**Tech Stack:** Markdown, YAML frontmatter, `skills` CLI, Agent Skills specification, Pixgen CLI, `uv_build`.

**Spec:** `docs/superpowers/specs/2026-10-09-pixgen-agent-skill-design.md`

## Global Constraints

- The skill directory and frontmatter `name` are both `pixgen-cli`.
- Keep the skill outside `src/` and out of the built Python distribution.
- Prefer a native image-generation tool for ordinary create/edit requests when the active harness exposes one.
- Check native tool availability in the active harness; do not assume every model or harness provides it.
- Use Pixgen for explicit Pixgen/provider/model requests, multi-provider comparisons, saved groups, and CLI-specific tasks.
- If native image generation is unavailable, use Pixgen only when the request calls for Pixgen or the user approves a separately billed provider API.
- Use `--json` only for commands that support it; interpret `schema_version`, command errors, target/variant results, and exit status together.
- Never expose provider API keys in commands or output.
- Keep references one level below `SKILL.md` and linked directly from it.

## Review Focus

- **Native tool unavailable:** Instructions must not claim universal availability; the fallback rule must require a Pixgen-directed request or user approval.
- **Explicit provider or model request:** Pixgen must take precedence over native generation.
- **Project-bound native output:** Instructions must place the selected asset in the requested or project-local path rather than leaving it only in a harness-managed location.
- **Pixgen partial failure:** Examples must distinguish successful targets from failed targets and interpret the exit status accordingly.
- **Unsupported `--json` or pre-result CLI errors:** Instructions must not parse human diagnostics as JSON or apply the flag to commands that do not support it.

---

### Task 1: Author the portable Pixgen skill

**Files:**
- Create: `skills/pixgen-cli/SKILL.md`
- Create: `skills/pixgen-cli/references/commands.md`

**Interfaces:**
- Consumes: Approved behavior and format requirements from the design spec.
- Produces: A named `pixgen-cli` Agent Skill; `SKILL.md` links directly to `references/commands.md` for detailed Pixgen command usage.

- [ ] **Step 1: Write `skills/pixgen-cli/SKILL.md`**

Use only `name` and `description` in YAML frontmatter. Match the directory name exactly. Keep the body focused on when to activate, native-tool priority, explicit Pixgen cases, the approval boundary for separately billed fallback, and common JSON/error workflow. Include the Review Focus cases in the instructions.

- [ ] **Step 2: Write `skills/pixgen-cli/references/commands.md`**

Document supported create/edit, reference-image, multi-model, group, model discovery/detail, and optimisation examples. Base flags on the repository README and current CLI help. State which commands accept `--json`; show the versioned result fields, target errors, and partial-failure exit behavior without inventing schema properties.

- [ ] **Step 3: Validate the skill format**

Run: `skills-ref validate skills/pixgen-cli`

Expected: validation succeeds for frontmatter, name constraints, and directory-name match.

- [ ] **Step 4: Verify named-skill discovery**

Run: `npx skills add . --list`

Expected: the discovered skill list includes `pixgen-cli`.

- [ ] **Step 5: Commit the skill files**

```bash
git add skills/pixgen-cli/SKILL.md skills/pixgen-cli/references/commands.md
git commit -m "docs: add Pixgen CLI agent skill"
```

### Task 2: Document installation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: The `pixgen-cli` skill created in Task 1.
- Produces: User-facing installation steps for project-scoped Claude Code and Codex use, plus a global install example.

- [ ] **Step 1: Add an Agent Skill section to `README.md`**

Show `npx skills add difegam/pixgen --skill pixgen-cli --agent claude-code --agent codex` for project installation and a `--global` variant for user-level installation. Explain that the skill prefers the active harness's native image tool for ordinary image requests, and that Pixgen itself must be installed for CLI workflows.

- [ ] **Step 2: Check the README edit**

Run: `git diff --check`

Expected: no whitespace errors; installation commands name only `pixgen-cli` and target the intended agents.

- [ ] **Step 3: Commit the README change**

```bash
git add README.md
git commit -m "docs: document Pixgen skill installation"
```

### Task 3: Verify packaging and repository checks

**Files:**
- Inspect: Built wheel and source distribution under `dist/`
- Verify: `skills/pixgen-cli/` and `README.md`

**Interfaces:**
- Consumes: Completed skill and install documentation from Tasks 1–2.
- Produces: Evidence that the skill installs independently and is excluded from Pixgen's Python distribution.

- [ ] **Step 1: Build the Python distributions**

Run: `uv build`

Expected: wheel and source distribution are produced successfully.

- [ ] **Step 2: Inspect both distribution archives**

Run: `unzip -l dist/pixgen-0.1.1-py3-none-any.whl` and `tar -tzf dist/pixgen-0.1.1.tar.gz`

Expected: neither archive contains `skills/pixgen-cli/`.

- [ ] **Step 3: Run repository lint and type checks**

Run: `just lint && just type-check`

Expected: both commands complete successfully.

- [ ] **Step 4: Review final changes and status**

Run: `git diff --check` and `git status --short`

Expected: no whitespace errors and only intended committed or uncommitted task changes remain.
