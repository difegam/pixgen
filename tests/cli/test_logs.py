"""Tests for CLI logging configuration."""

import logging
from typing import TYPE_CHECKING

import pytest

from pixgen.cli.logs import configure_logging, level_for_verbosity

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
def test_level_for_verbosity(verbosity: int, level: int) -> None:
    assert level_for_verbosity(verbosity) == level


def test_configure_logging_writes_to_stderr_only(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(1)

    logging.getLogger("pixgen.example").info("hello")

    captured = capsys.readouterr()
    assert "hello" in captured.err
    assert captured.out == ""


def test_configure_logging_is_idempotent() -> None:
    configure_logging(0)
    configure_logging(2)

    logger = logging.getLogger("pixgen")
    assert len(logger.handlers) == 1
    assert logger.level == logging.DEBUG
