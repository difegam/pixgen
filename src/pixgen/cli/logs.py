"""Configure process-wide logging for the console entry point."""

import logging
import sys

__all__: list[str] = [
    "configure_logging",
]

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


class _Formatter(logging.Formatter):
    """Format records, showing tracebacks only when the logger is at DEBUG.

    Tracebacks carry exception messages, which may echo provider responses or prompts, so
    they are an opt-in (``-vv``) detail.
    """

    def __init__(self, *, show_tracebacks: bool) -> None:
        super().__init__(_LOG_FORMAT)
        self._show_tracebacks = show_tracebacks

    def format(self, record: logging.LogRecord) -> str:
        """Format ``record``, dropping its traceback unless tracebacks are enabled."""
        if self._show_tracebacks or record.exc_info is None:
            return super().format(record)
        record = logging.makeLogRecord(record.__dict__)
        record.exc_info = None
        record.exc_text = None
        return super().format(record)


def _level_for_verbosity(verbosity: int) -> int:
    if verbosity <= 0:
        return logging.WARNING
    if verbosity == 1:
        return logging.INFO
    return logging.DEBUG


def configure_logging(verbosity: int) -> None:
    """Send ``pixgen`` log records to stderr at the level implied by ``verbosity``.

    ``0`` shows warnings and errors, ``1`` adds info and ``2`` or more adds debug detail and
    tracebacks. Only the ``pixgen`` logger is configured, so third-party libraries stay
    quiet. Stdout is never used, keeping ``--json`` output machine-readable. Calling this
    again replaces the handler it installed earlier.

    Args:
        verbosity: Number of times the verbose flag was given.
    """
    level = _level_for_verbosity(verbosity)
    logger = logging.getLogger("pixgen")
    for handler in tuple(logger.handlers):
        if not isinstance(handler, logging.NullHandler):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Formatter(show_tracebacks=level <= logging.DEBUG))
    logger.addHandler(handler)
    logger.setLevel(level)
