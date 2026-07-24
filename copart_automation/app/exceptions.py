"""Custom exceptions for the Copart automation project.

Each exception provides a clear, actionable message to assist in debugging
and user-facing error reporting. We intentionally avoid wrapping generic
exceptions in overly broad categories to maintain clarity.
"""

from __future__ import annotations


class CopartAutomationError(Exception):
    """Base exception for all Copart automation errors.

    Design decision: Using a common base allows callers to catch all
    project-specific errors with a single except clause, while still
    providing granular subclasses for targeted handling.
    """

    def __init__(self, message: str = "An automation error occurred.") -> None:
        super().__init__(message)
        self.message = message


class LoginFailure(CopartAutomationError):
    """Raised when authentication to Copart fails.

    This includes incorrect credentials, locked accounts, or any
    unexpected response during the login flow. We do not retry
    authentication to avoid account lockout policies.
    """


class SessionExpired(CopartAutomationError):
    """Raised when the stored Playwright session is no longer valid.

    The user must log in again to establish a fresh session.
    """


class NavigationError(CopartAutomationError):
    """Raised when navigation to an expected page fails or times out.

    Includes missing selectors, unexpected redirects, or page load
    failures that prevent reaching the target URL.
    """


class ParseError(CopartAutomationError):
    """Raised when expected data cannot be parsed from the page.

    Indicates the site structure may have changed or the data is
    unavailable to the authenticated account.
    """


class DownloadError(CopartAutomationError):
    """Raised when a file download fails or is interrupted.

    Covers network interruptions, missing download links, and
    file-system errors during save operations.
    """
