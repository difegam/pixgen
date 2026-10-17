"""Tests for CLI logging configuration."""

import logging
from typing import TYPE_CHECKING

import pytest

from pixgen.cli.logs import configure_logging

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _restore_pixgen_logger() -> Iterator[None]:
    logger = logging.getLogger("pixgen")
    handlers, level, propagate = list(logger.handlers), logger.level, logger.propagate
    yield
    logger.handlers[:] = handlers
    logger.setLevel(level)
    logger.propagate = propagate


@pytest.mark.parametrize(
    ("verbosity", "level"),
    [(0, logging.WARNING), (1, logging.INFO), (2, logging.DEBUG), (5, logging.DEBUG)],
)
def test_configure_logging_maps_verbosity_to_level(verbosity: int, level: int) -> None:
    configure_logging(verbosity)

    assert logging.getLogger("pixgen").level == level


def test_configure_logging_writes_to_stderr_only(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(1)

    logging.getLogger("pixgen.example").info("hello")

    captured = capsys.readouterr()
    assert "hello" in captured.err
    assert captured.out == ""


def test_configure_logging_is_idempotent() -> None:
    configure_logging(0)
    configure_logging(2)

    stream_handlers = [
        handler
        for handler in logging.getLogger("pixgen").handlers
        if not isinstance(handler, logging.NullHandler)
    ]
    assert len(stream_handlers) == 1


@pytest.mark.parametrize("verbosity", [1, 2])
def test_tracebacks_only_at_debug(verbosity: int, capsys: pytest.CaptureFixture[str]) -> None:
    shown = verbosity >= 2
    configure_logging(verbosity)

    try:
        raise RuntimeError("sensitive detail")
    except RuntimeError:
        logging.getLogger("pixgen.example").exception("failed")

    err = capsys.readouterr().err
    assert "ERROR pixgen.example: failed" in err
    assert ("Traceback" in err) is shown
    assert ("sensitive detail" in err) is shown


def test_library_logger_has_null_handler() -> None:
    import pixgen

    assert pixgen.__name__
    assert any(isinstance(h, logging.NullHandler) for h in logging.getLogger("pixgen").handlers)
