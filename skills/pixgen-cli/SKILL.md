---
name: pixgen-cli
description: Guides agents using Pixgen for image generation or editing, provider/model selection, provider comparisons, model groups, model discovery, and local image optimisation. Use for Pixgen CLI workflows; for ordinary image creation or editing, prefer a native image-generation tool exposed by the active harness.
---

# Pixgen CLI

Use Pixgen for explicit Pixgen workflows and its CLI-specific features. Pixgen
calls provider APIs and may incur separate usage charges.

## Choose the image-generation path

1. For ordinary image creation or editing, check whether the active harness
   exposes a native image-generation tool. If it does, use that tool and follow
   the harness's instructions for saving project-bound output. Check current
   tool availability; do not infer it from the model name or assume every
   harness or model has it.
2. Use Pixgen when the user explicitly requests Pixgen, a provider or model,
   multi-provider comparison, a saved model group, or a CLI-specific operation
   such as model discovery or local optimisation.
3. If native generation is unavailable and the request does not call for
   Pixgen, explain that using Pixgen would call a separately billed provider API
   and get the user's approval before switching. An explicit request to use
   Pixgen or a provider API is sufficient direction to use it.

## Use Pixgen

- Check `pixgen --help` if the installed CLI's command shape is unclear. Do not
  install Pixgen automatically; if it is missing, give the user
  `uv tool install pixgen`.
- Discover the installed catalogue with `pixgen model list --json`; it works
  offline and needs no provider credentials. Use
  `pixgen model get <provider/model> --json` for model-specific parameters and
  supported aspect ratios. Do not rely on a hard-coded catalogue.
- For generation, use `pixgen create`; for edits, use `pixgen edit` with the
  target image and any reference images. Use repeated `--model` flags for
  explicit multi-model runs. Use `--group` for a group the user requested;
  `--group` and `--model` are mutually exclusive.
- Use `pixgen optimize` for local image optimisation. It does not call a
  provider API.
- Prefer `--json` whenever the selected command supports it. Check command help
  instead of assuming all commands accept this flag.
- Parse JSON from stdout and inspect the process exit code. A command can
  partially succeed: report each successful artifact and each failed target.
  If the CLI returns a parse/help diagnostic instead of JSON, use that
  diagnostic and correct the command; do not parse it as JSON.
- Keep API keys in the documented environment variables. Never put keys in
  command arguments, generated files, or reported output.
- Do not pass `--force` unless the user asked to replace existing files. Report
  the final saved paths and any warnings or failures.

For command examples, supported JSON results, and exit statuses, read
[Pixgen command reference](references/commands.md).
