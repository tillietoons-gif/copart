"""Utility functions and retry decorators for the automation.

Design decisions:
- Tenacity is used for retry logic with exponential backoff.
- Retries are explicitly NOT applied to authentication to prevent
  account lockout. Only transient network failures and timeouts
  receive retries.
- Helper functions provide consistent path and URL handling.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from copart_automation.app.config import settings
from copart_automation.app.exceptions import CopartAutomationError
from copart_automation.app.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# Retry decorator for transient failures only (network/timeouts)
# Explicitly excludes LoginFailure and SessionExpired to avoid retrying auth.
retry_transient = retry(
    stop=stop_after_attempt(settings.retry_max_attempts),
    wait=wait_exponential(
        multiplier=settings.retry_backoff_multiplier,
        min=settings.retry_initial_delay,
        max=10.0,
    ),
    retry=retry_if_exception_type(
        (TimeoutError, ConnectionError, OSError)
    ),
    reraise=True,
    before_sleep=lambda retry_state: logger.info(
        f"Transient failure: {retry_state.outcome.exception()} — retrying in {retry_state.next_action.sleep} seconds..."
    ),
)


def safe_path_join(base: Path, *parts: str) -> Path:
    """Safely join paths, preventing directory traversal.

    Args:
        base: The base directory that must contain the final path.
        *parts: Path components to join.

    Returns:
        The resolved absolute path within the base directory.

    Raises:
        ValueError: If the resolved path escapes the base directory.
    """
    target = base.joinpath(*parts).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal detected: {target} is outside {base}")
    return target


def ensure_directory(path: Path) -> Path:
    """Create parent directories for a file or directory path if missing.

    Args:
        path: The file or directory path to prepare.

    Returns:
        The original path (now guaranteed to have existing parents).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def format_time_delta(seconds: float) -> str:
    """Format a time duration in a human-readable string.

    Used in logs and user-facing messages for timeout and retry reporting.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remaining = int(seconds % 60)
    return f"{minutes}m {remaining}s"


def extract_domain_from_url(url: str) -> str:
    """Extract the domain name from a full URL.

    Used for security checks when validating navigation targets.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc.lower()
