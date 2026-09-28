# Rich generation feedback implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show interactive users an animated, per-image Rich status display during generation and a coloured final result table without changing machine-readable or non-interactive output.

**Architecture:** `ImageApplication` reports provider-neutral job lifecycle events through an optional synchronous observer after preflight completes. A CLI-only `GenerationProgress` maps those events to a transient Rich `Progress` display on stderr; the command invoker creates it only for interactive, non-JSON runs. The existing renderer keeps JSON and non-interactive output stable while giving interactive final results a compact table.

**Tech stack:** Python 3.14, Rich 15.0.0, Pydantic 2, Cyclopts, pytest, pyrefly, Ruff, uv, just, prek.

**Spec:** [Approved design](../specs/2026-09-28-rich-generation-feedback-design.md)

## Global constraints

- Use the existing Rich 15.0.0 dependency. Do not add a dependency or a CLI flag.
- Activate live feedback only for a non-JSON command whose stdout and stderr are interactive terminals. JSON, pipes, files, CI, and dumb terminals retain their present durable output.
- JSON remains final-result-only on stdout, with no progress control sequences, colour codes, tables, or new diagnostics.
- Keep Rich and terminal I/O in `pixgen.cli`; `core` remains I/O-free and providers remain presentation-free.
- Preserve preflight, concurrency limits, request and run timeout behaviour, atomic artifact publication, result order, public errors, and exit codes.
- Use literal rendering for model IDs, paths, warnings, and provider messages. Keep Rich markup and highlighting disabled.
- Follow `.agents/skills/python-style/SKILL.md`, use fakes and temporary files in tests, and preserve existing uncommitted work.
- Before completion, run `just lint && just type-check && just test`.

## Review focus

- A preflight error produces no observer event or progress output because no image request was submitted. Task 1 tests this.
- A job cancelled by the shared run deadline still receives one terminal observer event with the existing `run deadline exceeded` message. Task 1 tests this.
- A queued job begins only after it obtains the semaphore, not when its task is created. Task 1 tests serialized variants.
- `--json` produces no live display and preserves valid JSON on stdout. Task 3 tests this.
- Redirected or dumb-terminal output must not contain ANSI cursor control sequences or change the current line-oriented result format. Task 3 tests this.

---

### Task 1: Report application job lifecycle without UI dependencies

**Files:**
- Modify: `src/pixgen/application.py:1-258`
- Modify: `tests/application/test_application.py`

**Interfaces:**
- Produces `@runtime_checkable class GenerationObserver(Protocol)` in `pixgen.application` with `run_started(self, plans: tuple[OutputPlan, ...]) -> None`, `job_started(self, plan: OutputPlan) -> None`, and `job_finished(self, plan: OutputPlan, result: TargetResult) -> None`.
- Extends `ImageApplication.run(..., observer: GenerationObserver | None = None) -> RunOutcome`.
- Extends `_execute_jobs(..., observer: GenerationObserver | None) -> list[TargetResult]` and `_run_job(..., observer: GenerationObserver | None) -> TargetResult` without changing their result or cancellation contracts.

- [ ] **Step 1: Write failing observer tests in `tests/application/test_application.py`**

Add a recording observer fake. For two variants with `max_parallel_requests=1`, assert the ordered events are one `run_started` tuple containing variants 1 and 2, then start/finish for variant 1, then start/finish for variant 2. Assert successful terminal events carry the same `TargetResult` returned by `run`.

- [ ] **Step 2: Add failing timeout and preflight tests**

Reuse `SlowProvider`, `CancellableProvider`, and `UnavailableProvider`. Assert a run-deadline cancellation emits exactly one terminal event for its synthetic timeout result, whose public message is `run deadline exceeded`. Assert unavailable credentials return exit code 2 and record no observer events.

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run: `uv run pytest tests/application/test_application.py -v`

Expected: FAIL because `GenerationObserver` and the `observer` parameter do not exist.

- [ ] **Step 4: Implement the provider-neutral lifecycle contract in `src/pixgen/application.py`**

Export the runtime-checkable protocol. After `plan_output` succeeds and immediately before task creation, call `observer.run_started(tuple(plans))` when supplied. Call `job_started(plan)` inside the semaphore block, before `provider.generate`. Build the existing success or recoverable-error `TargetResult`, call `job_finished(plan, result)`, then return it. When `_execute_jobs` creates a synthetic run-deadline timeout result for a cancelled task, send that same result to `job_finished` before appending it. Do not notify for failed preflight or change how unexpected `BaseException` failures cancel siblings.

- [ ] **Step 5: Run application tests and type checking**

Run: `uv run pytest tests/application/test_application.py -v && just type-check`

Expected: PASS. Existing timeout, sibling-cancellation, and result-order assertions remain green.

- [ ] **Step 6: Commit the lifecycle contract**

```bash
git add src/pixgen/application.py tests/application/test_application.py
git commit -m "feat: report image generation lifecycle"
```

### Task 2: Implement the CLI-only Rich progress observer and interactive result table

**Files:**
- Create: `src/pixgen/cli/progress.py`
- Modify: `src/pixgen/cli/render.py:1-40`
- Create: `tests/cli/test_progress.py`
- Create: `tests/cli/test_render.py`

**Interfaces:**
- Produces `GenerationProgress(console: Console)`, implementing `GenerationObserver` plus `stop(self) -> None`.
- `GenerationProgress` uses `Progress(..., console=console, transient=True)` with `SpinnerColumn`, `TextColumn`, and `TimeElapsedColumn`; it keys Rich task IDs by `(plan.model_id, plan.variant)`.
- Produces `create_generation_progress(*, as_json: bool) -> GenerationProgress | None` in `pixgen.cli.render`. It returns an observer only when `as_json` is false and both existing output consoles are interactive.
- Retains `render_command_result(result: CommandResult, *, as_json: bool) -> None`; for an interactive stdout terminal it renders a Rich table, otherwise it preserves the present line-oriented output.

- [ ] **Step 1: Write failing progress-observer tests in `tests/cli/test_progress.py`**

Construct `GenerationProgress` with a recording Rich `Console` forced interactive. Send a two-plan `run_started` event, a `job_started` event, a successful `job_finished` event with an artifact path, and a failed `job_finished` event with a `PublicError`. Assert the rendered record includes `1/2`, both canonical model/variant labels, and the terminal `Saved` and `Failed` states. Assert `stop()` clears the transient display and is safe after a preflight run that never called `run_started`.

- [ ] **Step 2: Write failing renderer tests in `tests/cli/test_render.py`**

Monkeypatch the module consoles with `Console(file=StringIO(), force_terminal=True, force_interactive=True, markup=False, highlight=False)` and assert an interactive mixed result renders table headers plus literal model IDs, artifact paths, warnings, and errors. With non-interactive consoles, assert the current `Run ID:` and indented line format remains. Assert `create_generation_progress(as_json=True)` and the non-interactive case both return `None`.

- [ ] **Step 3: Run the new CLI tests and confirm they fail**

Run: `uv run pytest tests/cli/test_progress.py tests/cli/test_render.py -v`

Expected: FAIL because the progress observer, factory, and interactive table do not exist.

- [ ] **Step 4: Implement `GenerationProgress` in `src/pixgen/cli/progress.py`**

Keep the module independent of providers and application construction. Start Rich lazily in `run_started`, create one queued row for each ordered plan with a 1/n custom field, and start a row only in `job_started`. Use a spinner while generating, dim queued text, green `Saved`, yellow `Saved with warnings`, and red `Failed`. `job_finished` must show the error message for failure and the artifact path for success. Use literal `Text` values rather than Rich markup for externally supplied strings. Set terminal rows complete to stop their spinner. `stop()` must stop only an already-started display.

- [ ] **Step 5: Implement the progress factory and final table in `src/pixgen/cli/render.py`**

Create `GenerationProgress` with the existing stderr console only when stdout and stderr are interactive, non-dumb, and the invocation is not JSON. Keep all JSON branches before any Rich rendering. For interactive successful and partial results, render one compact table with model, variant, status, and output or error; print Run ID separately. Keep preflight errors on stderr. Preserve the current line-oriented formatter for non-interactive output. Do not enable markup or auto-highlighting.

- [ ] **Step 6: Run the CLI tests and quality checks**

Run: `uv run pytest tests/cli/test_progress.py tests/cli/test_render.py -v && just lint && just type-check`

Expected: PASS. Captured JSON and non-interactive output contain no escape sequences; interactive captures contain the expected status text.

- [ ] **Step 7: Commit the CLI presentation layer**

```bash
git add src/pixgen/cli/progress.py src/pixgen/cli/render.py tests/cli/test_progress.py tests/cli/test_render.py
git commit -m "feat: show interactive generation progress"
```

### Task 3: Wire progress into invocation and protect output contracts end to end

**Files:**
- Modify: `src/pixgen/cli/invoke.py:1-39`
- Create: `tests/cli/test_invoke.py`
- Modify: `tests/cli/test_app.py`

**Interfaces:**
- `CommandInvoker.invoke(intent: ImageIntent, selection: ParameterSelection, options: ExecutionOptions) -> None` obtains a `GenerationProgress | None` through `create_generation_progress(as_json=options.as_json)`, passes it to `ImageApplication.run`, always calls `progress.stop()` after the run returns or raises, then renders the final `RunOutcome` and raises the existing `SystemExit`.
- `ExecutionOptions` and all Cyclopts command signatures remain unchanged. There is no `--verbose`, `--progress`, or other new public flag.

- [ ] **Step 1: Write failing invocation tests in `tests/cli/test_invoke.py`**

Use a fake application that captures the optional observer and returns a fixed `RunOutcome`. Monkeypatch the progress factory and final renderer. Assert a non-JSON invocation passes the factory result to `run`, stops it before final rendering, and preserves the outcome exit code. Assert a JSON invocation calls the factory with `as_json=True`, passes `None`, writes only the existing JSON result, and exits with the same code.

- [ ] **Step 2: Add a parser regression test in `tests/cli/test_app.py`**

Parse representative shared create and edit commands and assert their bound argument sets contain no new feedback option. This pins the deliberate no-new-flag decision while existing shared options continue to parse.

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run: `uv run pytest tests/cli/test_invoke.py tests/cli/test_app.py -v`

Expected: FAIL because the invoker does not request, pass, or stop a progress observer.

- [ ] **Step 4: Wire the observer lifecycle in `src/pixgen/cli/invoke.py`**

Create the observer before the application call. Use `try`/`finally` so `stop()` runs for successful results, preflight outcomes, cancellation, and unexpected raised failures. Pass it by the new `observer=` keyword. Keep result rendering and `SystemExit` after the progress is stopped, so durable output never appears inside a live Rich region.

- [ ] **Step 5: Run targeted regression tests**

Run: `uv run pytest tests/cli/test_invoke.py tests/cli/test_app.py tests/cli/test_progress.py tests/cli/test_render.py -v`

Expected: PASS. No command gains a feedback flag, JSON remains clean, and the progress display is always stopped before durable output.

- [ ] **Step 6: Run the full required verification and inspect the diff**

Run: `just lint && just type-check && just test`

Expected: all commands pass. Then run `git diff --check` and `git status --short`; confirm only feature files and the pre-existing baseline changes remain, with no generated artifacts or credentials.

- [ ] **Step 7: Commit the invocation wiring and tests**

```bash
git add src/pixgen/cli/invoke.py tests/cli/test_invoke.py tests/cli/test_app.py
git commit -m "feat: connect CLI generation progress"
```

## Plan self-review

The tasks cover every spec requirement: lifecycle events begin only after preflight, Rich exists only in the CLI, terminal activation is human-only, Rich uses transient per-target task rows, final tables are interactive-only, and JSON and redirected output retain their contracts. The review-focus cases have explicit owner tests. The plan adds no dependency, provider change, public option, network activity, or unrelated refactor.

No implementation work is authorised by this plan alone. Review it and choose an execution method before code changes begin.
