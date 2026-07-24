"""Centralized logging setup using Loguru.

Design decisions:
- Loguru is chosen over the standard logging module for its simpler
  configuration, built-in rotation, and structured formatting.
- Rotation is configured to prevent unbounded log growth on long-running
  automation tasks.
- All modules import from this file rather than configuring individually,
  ensuring consistent formatting and levels across the project.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger
from loguru._logger import Logger

from copart_automation.app.config import settings


def setup_logging() -> None:
    """Configure global logging with rotation and structured formatting.

    Removes the default logger sink and replaces it with a file sink
    that rotates based on size and retains logs for a configured period.
    A console sink is preserved for immediate visibility during
    development and debugging.
    """
    # Clear default sink
    logger.remove()

    # Console sink for visibility
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # File sink with rotation
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path),
        level=settings.log_level,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,  # Thread-safe for async environments
        backtrace=True,
        diagnose=True,
    )


def get_logger(name: str | None = None) -> Logger:
    """Return a named logger instance for module-level use.

    Args:
        name: Optional module identifier. Defaults to the bound logger.

    Returns:
        A Loguru logger instance with the configured sinks.
    """
    return logger.bind(name=name) if name else logger
