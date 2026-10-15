"""Configure process-wide logging for the console entry point."""

import logging
import sys

__all__: list[str] = [
    "configure_logging",
    "level_for_verbosity",
]

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def level_for_verbosity(verbosity: int) -> int:
    """Map a count of ``-v`` flags to a logging level.

    Args:
        verbosity: Number of times the verbose flag was given.

    Returns:
        ``WARNING`` for 0, ``INFO`` for 1 and ``DEBUG`` for 2 or more.
    """
    if verbosity <= 0:
        return logging.WARNING
    if verbosity == 1:
        return logging.INFO
    return logging.DEBUG


def configure_logging(verbosity: int) -> None:
    """Send ``pixgen`` log records to stderr at the level implied by ``verbosity``.

    Only the ``pixgen`` logger is configured, so third-party libraries stay quiet.
    Stdout is never used, keeping ``--json`` output machine-readable.

    Args:
        verbosity: Number of times the verbose flag was given.
    """
    logger = logging.getLogger("pixgen")
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(level_for_verbosity(verbosity))
    logger.propagate = False
