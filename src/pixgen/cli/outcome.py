"""Map command results to rendered output and process exit statuses."""

import functools
import inspect
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Final

from pydantic import ValidationError

from pixgen.cli.render import (
    render_command_result,
    render_group_create_result,
    render_group_list_result,
    render_model_get_result,
    render_model_list_result,
    render_optimize_result,
)
from pixgen.core.errors import ErrorCode, PixgenError, validation_message
from pixgen.core.results import (
    CommandResult,
    GroupCreateResult,
    GroupListResult,
    ModelGetResult,
    ModelListResult,
    OptimizeResult,
    PublicError,
    VariantStatus,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: list[str] = [
    "RESULT_ACTION",
    "CliOutcome",
    "ExitStatus",
    "PublicResult",
    "cli_command",
    "command_error",
    "exit_status",
    "failure_outcome",
    "render_outcome",
]

type PublicResult = (
    CommandResult
    | GroupCreateResult
    | GroupListResult
    | ModelGetResult
    | ModelListResult
    | OptimizeResult
)


class ExitStatus(IntEnum):
    """Process exit statuses; 1 is left to Cyclopts for command-line parse errors."""

    SUCCESS = 0
    REJECTED = 2
    ALL_FAILED = 3
    PARTIAL_FAILURE = 4


def exit_status(result: PublicResult) -> ExitStatus:
    """Return the exit status a public result warrants."""
    if result.error is not None:
        return ExitStatus.REJECTED
    if isinstance(result, OptimizeResult):
        failures = sum(variant.status is VariantStatus.FAILED for variant in result.variants)
        completed = sum(variant.status is VariantStatus.COMPLETED for variant in result.variants)
        if failures:
            return ExitStatus.PARTIAL_FAILURE if completed else ExitStatus.ALL_FAILED
    if isinstance(result, CommandResult):
        failures = sum(target.error is not None for target in result.results)
        if failures == len(result.results):
            return ExitStatus.ALL_FAILED
        if failures:
            return ExitStatus.PARTIAL_FAILURE
    return ExitStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class CliOutcome:
    """A command's public result together with how to render it."""

    result: PublicResult
    as_json: bool
    relative_output_paths: bool = False
    as_tree: bool = False

    def __cyclopts_returncode__(self) -> int:
        return exit_status(self.result)


def render_outcome[T](outcome: T) -> T:
    """Render a command outcome; pass through Cyclopts built-ins such as help and version."""
    if not isinstance(outcome, CliOutcome):
        return outcome
    match outcome.result:
        case CommandResult() as result:
            render_command_result(
                result,
                as_json=outcome.as_json,
                relative_output_paths=outcome.relative_output_paths,
            )
        case GroupCreateResult() as result:
            render_group_create_result(result, as_json=outcome.as_json)
        case GroupListResult() as result:
            render_group_list_result(result, as_json=outcome.as_json)
        case ModelGetResult() as result:
            render_model_get_result(result, as_json=outcome.as_json)
        case ModelListResult() as result:
            render_model_list_result(result, as_json=outcome.as_json, as_tree=outcome.as_tree)
        case OptimizeResult() as result:
            render_optimize_result(
                result,
                as_json=outcome.as_json,
                relative_output_paths=outcome.relative_output_paths,
            )
    return outcome


RESULT_ACTION: Final = (render_outcome, "sys_exit")


def command_error(error: PublicError) -> CommandResult:
    """Wrap a command-level error in an image command result."""
    return CommandResult(run_id=uuid.uuid7(), error=error)


def _public_error(exc: PixgenError | ValidationError) -> PublicError:
    if isinstance(exc, PixgenError):
        return PublicError(code=exc.code, message=exc.message)
    return PublicError(code=ErrorCode.INVALID_REQUEST, message=validation_message(exc))


def failure_outcome(
    exc: PixgenError | ValidationError,
    *,
    as_json: bool,
    error_result: Callable[[PublicError], PublicResult] = command_error,
) -> CliOutcome:
    """Return the rejected outcome for an expected command failure."""
    return CliOutcome(error_result(_public_error(exc)), as_json=as_json)


def cli_command[**P](
    error_result: Callable[[PublicError], PublicResult] = command_error,
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """Turn expected failures in a command into rejected outcomes.

    The command must accept a ``json`` keyword, which selects the error rendering.
    Unexpected exceptions propagate unchanged.
    """

    def decorate(command: Callable[P, Any]) -> Callable[P, Any]:

        # Handle asynchronous commands.
        if inspect.iscoroutinefunction(command):

            @functools.wraps(command)
            async def run_async(*args: P.args, **kwargs: P.kwargs) -> Any:
                try:
                    return await command(*args, **kwargs)
                except (PixgenError, ValidationError) as exc:
                    return failure_outcome(
                        exc, as_json=bool(kwargs.get("json")), error_result=error_result
                    )

            return run_async

        # Handle synchronous commands.
        @functools.wraps(command)
        def run(*args: P.args, **kwargs: P.kwargs) -> Any:
            try:
                return command(*args, **kwargs)
            except (PixgenError, ValidationError) as exc:
                return failure_outcome(
                    exc, as_json=bool(kwargs.get("json")), error_result=error_result
                )

        return run

    return decorate
