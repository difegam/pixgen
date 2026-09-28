# Rich generation feedback

**Status:** Approved direction; implementation plan awaiting review

**Date:** 2026-09-28

## Goal

Give people using Pixgen in an interactive terminal immediate, per-image feedback while generation runs. The display must show the target's position in the run, model and variant, and its current state. It must never alter JSON output, pipeline output, provider behaviour, artifact writing, timeout handling, or exit codes.

## Scope and constraints

- Use the already locked Rich 15.0.0 dependency. Do not add a dependency or a command-line flag.
- Activate the live display only for non-JSON invocations whose Rich stdout and stderr consoles are interactive. Piped output, files, CI, and dumb terminals retain the existing durable plain-text result output.
- Treat `--json` as an exact machine-readable contract. It writes only the final JSON result to stdout, with no progress frames, colour codes, tables, or diagnostics added by this feature.
- Keep Rich imports and terminal I/O in `pixgen.cli`. `pixgen.core` remains I/O-free and providers remain unaware of terminal presentation.
- Preserve all existing preflight, concurrency, cancellation, partial-failure, artifact, result-order, and exit-code behaviour.
- Preserve untrusted model IDs, paths, warning text, and provider error messages as literal text. Existing consoles keep `markup=False` and `highlight=False`.

## Lifecycle and data flow

`ImageApplication` exposes a small synchronous `GenerationObserver` protocol in `application.py`. It reports only provider-neutral execution facts:

1. After all local preflight and output planning succeeds, report the complete, ordered tuple of `OutputPlan` targets.
2. When a target acquires the request semaphore, report that it has begun generation.
3. When generation and atomic publication produce a `TargetResult`, report that terminal result. When a run deadline cancels a target, report the synthetic timeout result before returning it.

The CLI creates a `GenerationProgress` observer only for an interactive, non-JSON command and passes it to `ImageApplication.run`. The observer manages a Rich `Progress` instance on stderr. It creates one row per planned target, showing its 1/n position, canonical model ID, variant, status, and elapsed time. Queued rows are dim, active rows use a spinner, successful rows are green, warnings are yellow, and failed rows are red. The display uses `transient=True`, so it disappears before the existing durable result rendering begins.

The final interactive human result becomes a compact Rich table with Run ID, model, variant, outcome, and artifact path or public error. Warnings remain distinct from failures. Non-interactive human output retains the present line-oriented format.

## Rich API decisions

Use `Progress` with `SpinnerColumn`, `TextColumn`, and `TimeElapsedColumn`. Add each queued target using `total=None` and custom fields for its ordinal and status. On state transitions, use `update()` to change the field values; mark terminal rows complete so the spinner stops. Use `transient=True` so no live frames remain in scrollback.

The invocation layer decides activation only when both output consoles are interactive terminals. Rich's own `Console.is_terminal` and `Console.is_dumb_terminal` semantics protect streams and unsupported terminals. The progress display writes to stderr so stdout remains available for the command's established result stream.

## Acceptance criteria

- A single interactive target displays an animated `1/1` generation row and then a final table.
- A multi-target interactive run displays a row for every planned `(model, variant)` target. Rows move from queued to generating and then saved or failed as concurrent jobs complete.
- A target that times out at the run deadline is shown as failed with the existing `run deadline exceeded` public message.
- A preflight failure starts no progress display.
- JSON and non-interactive human output contain no progress control sequences and retain their current result structure.
- No test performs a real API request, reads user files, or depends on wall-clock refresh timing.

## Research

Context7 resolved Rich as [`/textualize/rich`](https://github.com/textualize/rich). Its current documentation confirms `Progress.add_task(..., total=None, **fields)`, `Progress.update(..., **fields)`, and `transient=True` for temporary displays, plus `Console.is_terminal` and `Console.is_dumb_terminal` for terminal capability checks. See [Rich progress documentation](https://rich.readthedocs.io/en/latest/progress.html) and [Rich console documentation](https://rich.readthedocs.io/en/latest/console.html).
