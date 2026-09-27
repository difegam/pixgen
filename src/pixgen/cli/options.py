"""Define common image command execution options."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

__all__: list[str] = ["ExecutionOptions"]


class ExecutionOptions(BaseModel):
    """Options shared by provider-owned image commands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variants: int = Field(default=1, ge=1)
    output: Path | None = None
    output_dir: Path | None = None
    mkdir: bool = False
    force: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1)
    as_json: bool = Field(
        default=False,
        validation_alias="json",
        serialization_alias="json",
        description="Render the result as JSON",
    )
