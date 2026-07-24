"""Session lifecycle management for Copart automation.

Design decisions:
- Session management is separated from authentication to allow
  independent testing and reuse in different workflows.
- The session layer checks for expiration before each major operation,
  providing an automatic refresh mechanism without requiring user
  intervention unless reauthentication fails.
- Storage state files are versioned implicitly by timestamp; old
  sessions are overwritten rather than accumulated.
"""

from __future__ import annotations

from copart_automation.app.auth import AuthManager, COPART_DASHBOARD_URL
from copart_automation.app.browser import BrowserManager
from copart_automation.app.config import settings
from copart_automation.app.exceptions import SessionExpired
from copart_automation.app.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Orchestrates the lifecycle of an authenticated automation session.

    Provides a single entry point for initializing, verifying, and
    refreshing sessions. Callers should prefer this manager over
    using AuthManager directly to ensure consistent session checks.
    """

    def __init__(self, browser_manager: BrowserManager | None = None) -> None:
        self._browser = browser_manager or BrowserManager()
        self._auth = AuthManager(self._browser)
        self._is_initialized = False

    @property
    def auth(self) -> AuthManager:
        return self._auth

    @property
    def browser(self) -> BrowserManager:
        return self._browser

    async def initialize(self) -> bool:
        """Initialize the session by loading or creating an authenticated session.

        Returns:
            True if an authenticated session is ready.
        """
        if self._is_initialized:
            # Verify existing session is still valid
            if await self._auth.verify_authentication():
                logger.info("Existing initialized session verified.")
                return True
            else:
                logger.info("Existing session expired; will re-authenticate.")

        # Try loading previous session
        loaded = await self._auth.load_existing_session()
        if loaded:
            self._is_initialized = True
            if await self._auth.verify_authentication():
                logger.info("Loaded session verified successfully.")
                return True
            else:
                logger.info("Loaded session invalid; will re-authenticate.")
                self._is_initialized = False

        # Perform fresh login
        try:
            await self._browser.start()
            success = await self._auth.login()
            if success:
                self._is_initialized = True
                logger.info("New session initialized successfully.")
                return True
            else:
                logger.warning("Login returned False without exception (possible MFA pending).")
                # Even if login returns False, check if we have a session
                if await self._auth.verify_authentication():
                    self._is_initialized = True
                    logger.info("Session established after partial login flow.")
                    return True
                raise SessionExpired("Login did not establish a valid session.")
        except Exception as exc:
            logger.error(f"Session initialization failed: {exc}")
            raise

    async def verify_session(self, auto_reauth: bool = True) -> bool:
        """Verify that the current session is still valid.

        Args:
            auto_reauth: If True, attempt reauthentication on expiration.

        Returns:
            True if session is valid; False otherwise.
        """
        if not self._is_initialized:
            logger.info("Session not initialized; initializing now.")
            return await self.initialize()

        valid = await self._auth.verify_authentication()
        if valid:
            logger.debug("Session verified: valid.")
            return True

        logger.info("Session expired or invalid.")
        if auto_reauth:
            logger.info("Attempting automatic re-authentication.")
            success = await self._auth.reauthenticate()
            if success:
                self._is_initialized = True
                return True
            else:
                logger.error("Automatic re-authentication failed.")
                self._is_initialized = False
                return False
        else:
            self._is_initialized = False
            return False

    async def close(self) -> None:
        """Close the session and browser resources cleanly."""
        logger.info("Closing session manager.")
        await self._auth.save_session()
        await self._browser.close()
        self._is_initialized = False

    async def __aenter__(self) -> SessionManager:
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
