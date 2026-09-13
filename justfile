
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set dotenv-load

[doc("Available recipes")]
[private]
default:
    @just --list --list-submodules

[doc("Initialize the project")]
[group("development")]
init:
    @echo "Initializing the project..."
    @uv sync --all-groups
    @uv run prek install --prepare-hooks --hook-type pre-commit --hook-type pre-push
    @echo "Project initialized successfully!"

[doc("Run the application locally")]
[group("application")]
run:
    uv run app

[doc("Run linter and formatter")]
[group("code-quality")]
lint:
    uv run ruff check --fix
    uv run ruff format

[doc("Run prek hooks on all files")]
[group("code-quality")]
check:
    @echo "Running prek hooks on all files"
    @uv run prek run --all-files

[doc("Update prek hook revisions with a 7-day cooldown")]
[group("development")]
hooks-update:
    uv run prek auto-update --cooldown-days 7

[doc("Run tests")]
[group("code-quality")]
test:
    echo "🧪 Testing app...! "
    @uv run pytest --tb=short -s tests/

# ⚠ Type checker: choose ONE of type-check-ty or type-check-mypy (not both)

[doc("Type-check with ty (choose ty OR mypy, not both) — https://docs.astral.sh/ty/")]
[group("code-quality")]
type-check-ty:
    uv run ty check

[doc("Update project dependencies")]
[group("development")]
update:
    uv lock --upgrade && uv sync --all-groups
    @echo "✅ Dependencies updated successfully 🚀"

[doc("Remove temporary files")]
[group("development")]
clean:
    rm -rf .venv .pytest_cache .mypy_cache .ty_cache .ruff_cache .coverage htmlcov
    find . -type d -name "__pycache__" -exec rm -r {} +

[doc("Recreate the virtual environment from scratch")]
[group("development")]
fresh: clean init
    uv run prek cache clean
    @echo "✅ Fresh setup complete, ready to code 🚀"
