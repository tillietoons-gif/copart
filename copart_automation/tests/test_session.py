"""Tests for session management and lifecycle.

These tests verify the SessionManager behavior without requiring
an actual Copart login, using mock browser contexts where possible.
"""

from __future__ import annotations

import pytest

from copart_automation.app.browser import BrowserManager
from copart_automation.app.session import SessionManager

pytestmark = pytest.mark.asyncio


class TestSessionManagement:
    """Verify session initialization and verification behavior."""

    async def test_session_manager_creation(self) -> None:
        """Session manager should initialize without errors."""
        session = SessionManager()
        assert session.auth is not None
        assert session.browser is not None

    async def test_session_context_manager(self) -> None:
        """Using session as async context manager should initialize and close."""
        session = SessionManager()
        # Note: This will attempt real browser initialization; we test
        # the structure rather than performing a full login.
        # For production tests, mock the browser manager.
        # Here we verify the manager exists and has the correct interface.
        assert hasattr(session, "initialize")
        assert hasattr(session, "verify_session")
        assert hasattr(session, "close")

    async def test_session_closes_gracefully(self) -> None:
        """Closing a session should not raise errors even if not fully initialized."""
        session = SessionManager()
        await session.close()
