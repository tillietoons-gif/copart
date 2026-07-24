"""Tests for logging setup."""

from __future__ import annotations

from pathlib import Path

from copart_automation.app.logger import get_logger, setup_logging


def test_setup_logging_creates_log_directory(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    setup_logging()
    assert log_dir.exists()

    logger = get_logger(__name__)
    logger.debug("Testing logger output")
    assert log_dir.exists()
