# AGENTS.md

## Commands

```bash
just init          # uv sync + install prek hooks
just lint          # ruff check --fix + ruff format
just type-check    # pyrefly check (NOT mypy)
just test          # pytest
just check         # prek run --all-files (full hook suite)
```

Run `just lint && just type-check && just test` before claiming done. Single test file: `uv run pytest tests/path/to/test_file.py`.

## Layout

- `src/pixgen/cli/` — cyclopts commands, rendering, exit codes. Never imports providers.
- `src/pixgen/core/` — provider-neutral types, intents, results, errors. No I/O.
- `src/pixgen/images/` — reads local inputs, returns bytes + metadata; decodes, resizes, and encodes pixels with Pillow.
- `src/pixgen/providers/` — OpenAI, Gemini, and OpenRouter adapters behind `ImageProvider` protocol.
- `src/pixgen/application.py` — orchestration: preflight, variants, concurrency, results.
- `src/pixgen/optimization/` — local `pixgen optimize`: request models, planning, and execution. Never imports providers.
- `src/pixgen/artifacts.py` — atomic file writes via temp-file + rename.
- `src/pixgen/runtime.py` — composition root. Builds everything, injects clients.
- `src/pixgen/config/` — pydantic-settings, PlatformDirs, `pixgen.toml`.
- `tests/` — mirrors `src/pixgen/` structure. Factories in `tests/factories.py`.

## Conventions

- **Python 3.14**. Use `X | Y` unions and `list[str]` generics. Annotations are lazily evaluated, so do not add `from __future__ import annotations`.
- **British English** in docstrings ("Initialise", "Serialise").
- **Google-style** docstrings. Frozen Pydantic models. `StrEnum` for enums.
- **Type checker is pyrefly**, not mypy. Config in `pyrefly.toml`.
- **asyncio_mode = "auto"** — do not add `@pytest.mark.asyncio` decorators.
- **Pre-commit runs via `prek`**, not `pre-commit`. Hooks defined in `.pre-commit-config.yaml`.

## Architecture notes

- No database. Output = local artifact files + returned result.
- Providers are not plugins. The `ImageProvider` protocol is internal.
- `runtime.py` creates only the clients the selected command needs (`model list` needs no credentials).
- Provider keys: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY` env vars only. Never in config files or logs.
- `pixgen.toml` is runtime defaults (model lists, concurrency limits), not dev config.

## Testing

- `pythonpath = "src"` in pyproject — imports use `from pixgen...`, not relative paths.
- Use `tmp_path`, monkeypatching, or fakes. No real network, credentials, or user files.
