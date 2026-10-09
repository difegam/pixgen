# Pixgen Agent Skill Design

## Goal

Provide a portable, installable Agent Skill that teaches coding agents to use
Pixgen's CLI reliably for image creation, editing, model discovery, model groups,
and local image optimisation. The skill must work with Claude Code and clients
that implement the open Agent Skills format, and it must stay out of the
published Python package.

## User and success criteria

The user is a person or coding agent that has Pixgen installed and needs to
complete an image task from a shell. The skill succeeds when an agent can:

- discover the installed CLI's command surface and supported models;
- construct a valid command for the requested image operation;
- use structured output where the command supports it;
- distinguish command rejection, total failure, partial failure, and success;
- report generated artifact paths and errors accurately; and
- install the skill into Claude Code or another supported agent using the
  `skills` CLI.

## Approved design

### Distribution and compatibility

Keep one canonical skill at `skills/pixgen-cli/`. Do not duplicate the skill
under `.claude/skills/` or `.agents/skills/`; the `skills` CLI installs the
selected source into the target agent's skill directory. Document installation
from the Pixgen GitHub repository in the README, including Claude Code and Codex
examples and project or global scope as appropriate.

Use the portable Agent Skills `SKILL.md` format. The directory and frontmatter
`name` must both be `pixgen-cli`. Keep frontmatter to the portable `name` and
`description` fields; describe shell and Pixgen requirements in the body rather
than relying on optional client-specific metadata. Store the skill outside
`src/` so it is not part of the Python import package. Verify the built
distribution does not contain the skill.

### Agent workflow and CLI contract

The skill treats the installed Pixgen CLI as the operative contract:

1. Check whether `pixgen` is available and consult `pixgen --help` if the
   installed command surface is unclear.
2. Discover models with `pixgen model list --json`. Use
   `pixgen model get <provider/model> --json` when operation parameters or
   aspect-ratio support need detail. Do not hard-code a model catalogue.
3. Choose `create`, `edit`, `optimize`, or a model-group command based on the
   user's requested task. Use repeated `--model` options for explicit
   multi-model fan-out; use `--group` when the user asks for a saved group.
4. Add `--json` to commands that support structured results. Parse JSON from
   stdout rather than interpreting human-formatted output. Respect
   `schema_version`, command-level `error`, and per-target or per-variant
   outcomes. Use both the JSON result and process exit code; do not equate a
   non-zero partial-failure status with total failure or claim success for
   failed targets.
5. Report saved artifact paths, successful targets, warnings, and failures.
   Never expose provider API keys in commands or output; credentials are
   supplied through the documented environment variables.

Do not assume every command accepts `--json`; the skill and reference must only
use flags supported by that command. If CLI parsing fails before a JSON result is
produced, use the diagnostic/help output rather than attempting to parse it as
JSON.

### Content layout

Keep `SKILL.md` concise and focused on activation, command discovery, JSON/error
handling, and the common workflow. Put the command matrix and representative
examples in one directly linked file under `skills/pixgen-cli/references/` if
needed to keep the main skill compact. Keep references one level below
`SKILL.md`; avoid nested reference chains. Derive command examples from the
README and CLI help so they match Pixgen's actual syntax.

The examples should cover:

- create and edit with explicit models and output paths;
- edit reference images and common shared options;
- multi-model generation and model groups;
- offline model discovery and model details;
- local optimisation; and
- handling structured success, rejection, and partial-failure results.

### Documentation and validation

Add a short README section explaining the skill, the `skills` CLI install
command, and the supported agent targets. Use `skills add`'s named-skill option
so users install only `pixgen-cli`, not every skill that may later be added to
the repository.

Validate the directory name and frontmatter against the Agent Skills
specification, confirm the `skills` CLI discovers the skill by name, and inspect
the built Python package artifact to confirm it excludes `skills/`. Run the
repository lint and type-check commands required for a completion claim. Since
this change adds documentation only, validation focuses on the skill format,
installer discovery, and package contents.

## Alternatives considered

1. **One canonical skill under `skills/` (selected):** portable, compatible with
   the `skills` CLI's named-skill installation, and avoids duplicate
   instructions.
2. **Duplicate copies under Claude and generic agent directories:** directly
   discoverable without an installer in some clients, but creates multiple
   copies that can drift and is unnecessary for the requested `skills` CLI
   distribution.
3. **README instructions only:** simplest to maintain, but not a discoverable
   or installable Agent Skill.

## Non-goals

- Do not add Pixgen skill files to the Python runtime package or package data.
- Do not add CLI functionality, change JSON schemas, or add provider support.
- Do not create separate skills for individual Pixgen commands.
- Do not install the skill or Pixgen into the user's global environment as part
  of authoring the repository skill.

## Research references

- [Agent Skills specification](https://agentskills.io/specification)
- [Claude Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Claude Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [`skills` CLI documentation](https://www.skills.sh/docs/cli)
- [`skills` CLI source README](https://github.com/vercel-labs/skills#readme)
- [Pixgen README](https://github.com/difegam/pixgen#readme)
