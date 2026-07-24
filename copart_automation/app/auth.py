"""Authentication manager for Copart account access.

Design decisions:
- Playwright's storage_state mechanism is used to persist cookies,
  localStorage, and session data between runs. This avoids requiring
  the user to log in on every execution.
- Authentication retries are intentionally NOT implemented; repeated
  failed login attempts can trigger account security measures.
- If multi-factor authentication (MFA) is required by Copart, the
  workflow pauses and guides the user to complete verification
  rather than attempting to bypass it automatically.
"""

from __future__ import annotations

import time
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from copart_automation.app.browser import BrowserManager
from copart_automation.app.config import settings
from copart_automation.app.exceptions import LoginFailure, SessionExpired
from copart_automation.app.logger import get_logger
from copart_automation.app.utils import retry_transient

logger = get_logger(__name__)

# Official Copart login endpoint (publicly documented)
# Note: This URL may change; users should verify in .env or docs.
COPART_LOGIN_URL = "https://www.copart.com/login"
COPART_DASHBOARD_URL = "https://www.copart.com/"


class AuthManager:
    """Handles login, session persistence, and authentication verification.

    This manager does not attempt to bypass any anti-bot or security
    measures implemented by Copart. If additional verification is
    required, the user is explicitly guided through it.
    """

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._manager = browser_manager
        self._context: BrowserContext | None = None

    @property
    def context(self) -> BrowserContext | None:
        return self._context

    async def load_existing_session(self) -> bool:
        """Attempt to load a previously saved authentication session.

        Returns:
            True if a valid session was loaded; False otherwise.
        """
        state_path = settings.storage_state_path
        if not state_path.exists():
            logger.info("No existing session file found at %s", state_path)
            return False

        logger.info("Attempting to load existing session from %s", state_path)
        try:
            new_context = await self._manager._browser.new_context(
                storage_state=str(state_path),
                accept_downloads=True,
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            )
            # Verify the session by navigating to the dashboard
            page = await new_context.new_page()
            await page.goto(COPART_DASHBOARD_URL, timeout=settings.navigation_timeout)
            # Wait for a known dashboard element or redirect to login
            try:
                await page.wait_for_selector(
                    "a[href*='dashboard'], .dashboard, #main",  # Example selectors
                    timeout=5000,
                )
            except Exception:
                # If we don't find dashboard indicators quickly, check if
                # we're redirected to login
                current_url = page.url
                if "/login" in current_url or "/signin" in current_url:
                    logger.info("Existing session expired; redirect detected.")
                    await new_context.close()
                    return False

            # If we reach a non-login page, assume session is valid
            self._context = new_context
            logger.info("Existing session loaded successfully.")
            await page.close()
            return True
        except Exception as exc:
            logger.warning(f"Failed to load existing session: {exc}")
            return False

    @retry_transient
    async def login(self, email: str | None = None, password: str | None = None) -> bool:
        """Perform authentication with the Copart website.

        Args:
            email: Copart account email. Defaults to settings.
            password: Copart account password. Defaults to settings.

        Returns:
            True if login succeeds; False if additional verification is needed.

        Raises:
            LoginFailure: If authentication fails due to invalid credentials
                or an unrecoverable error.
        """
        email = email or settings.copart_email
        if not email or not settings.copart_password.get_secret_value():
            raise LoginFailure(
                "Email or password not configured. Check your .env file."
            )

        # Ensure browser manager is started
        if not self._manager.is_active():
            await self._manager.start()

        # Create a fresh context for this login attempt
        # We do this to avoid contaminating any existing session context
        if self._manager.get_context():
            await self._manager.close()
            await self._manager.start()

        self._context = self._manager.get_context()
        if self._context is None:
            raise LoginFailure("Browser context could not be initialized.")

        page = await self._context.new_page()
        try:
            logger.info("Navigating to Copart login page: %s", COPART_LOGIN_URL)
            await page.goto(COPART_LOGIN_URL, timeout=settings.navigation_timeout, wait_until="networkidle")

            # Wait for the login form to appear (site-specific selectors)
            # We use generic selectors that are resilient to minor changes.
            try:
                await page.wait_for_selector(
                    "input[type='email'], input[name='email'], input[type='text']",
                    timeout=settings.action_timeout,
                )
            except Exception as exc:
                raise LoginFailure(
                    f"Login form did not load. The page structure may have changed. Details: {exc}"
                ) from exc

            # Fill credentials
            email_input = await page.query_selector("input[type='email'], input[name='email']")
            if email_input:
                await email_input.fill(email)
            else:
                # Fallback to first text input
                await page.fill("input[type='text']", email)

            password_input = await page.query_selector("input[type='password']")
            if password_input:
                await password_input.fill(settings.copart_password.get_secret_value())
            else:
                await page.fill("input[type='password']", settings.copart_password.get_secret_value())

            logger.info("Credentials filled (email=%s)", email)

            # Click submit
            submit_button = await page.query_selector(
                "button[type='submit'], input[type='submit'], button:has-text('Log In'), button:has-text('Sign In')"
            )
            if submit_button:
                await submit_button.click()
            else:
                await page.keyboard.press("Enter")

            # Wait for navigation after submit (either success or failure)
            try:
                await page.wait_for_load_state("networkidle", timeout=settings.navigation_timeout)
            except Exception:
                # Timeout during navigation is acceptable; check current state
                pass

            # Check for additional verification / MFA
            current_url = page.url
            if "/verify" in current_url or "/mfa" in current_url or "/challenge" in current_url:
                logger.info("Additional verification required. Pausing for user interaction.")
                print("\n=== ADDITIONAL VERIFICATION REQUIRED ===")
                print("The Copart site requires additional verification (e.g., MFA, CAPTCHA).")
                print("Please complete the verification in the browser window.")
                print("After verification, press ENTER in this terminal to continue...")
                try:
                    input()
                except EOFError:
                    # Non-interactive mode; log and proceed cautiously
                    logger.warning("Non-interactive mode: cannot wait for user input.")
                    pass
                # After user completes verification, continue
                await page.wait_for_navigation(timeout=30000)

            # Verify success: check for dashboard indicators or absence of login
            current_url_after = page.url
            if "/login" in current_url_after and "/dashboard" not in current_url_after:
                # Check for explicit error messages
                error_text = await page.text_content(".error-message, .alert-danger, .login-error")
                if error_text:
                    logger.error("Login failed with error message: %s", error_text)
                    raise LoginFailure(f"Login rejected by Copart: {error_text}")
                # If we're back at login and no dashboard indicators exist,
                # assume failure
                logger.error("Login failed: redirected back to login page without success indicators.")
                raise LoginFailure("Login failed: redirected back to login page. Check credentials.")

            logger.info("Login successful. Current URL: %s", current_url_after)

            # Save session state for future reuse
            await self.save_session()
            return True
        finally:
            # We do NOT close the page immediately because the caller
            # will continue using the context. However, we should close
            # the login-specific page if it is separate from the context.
            pass

    async def save_session(self) -> None:
        """Persist the current browser context session to disk.

        Allows future automation runs to reuse authentication without
        requiring credentials again, as long as the session remains
        valid according to Copart's session policies.
        """
        if not self._context:
            logger.warning("No active context to save.")
            return

        state_path = settings.storage_state_path
        state_path.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(state_path))
        logger.info("Session saved to %s", state_path)

    async def verify_authentication(self) -> bool:
        """Check whether the current context has a valid session.

        Returns:
            True if the session is valid; False otherwise.
        """
        if not self._context:
            return False

        page = await self._context.new_page()
        try:
            await page.goto(COPART_DASHBOARD_URL, timeout=settings.navigation_timeout)
            # Look for elements that indicate a logged-in state
            # We avoid relying on a single selector to improve resilience.
            indicators = [
                "a[href*='logout']",
                ".user-menu",
                ".dashboard",
                "a[href*='search']",
            ]
            for selector in indicators:
                try:
                    await page.wait_for_selector(selector, timeout=3000)
                    logger.info("Authentication verified (indicator: %s)", selector)
                    return True
                except Exception:
                    continue
            # If no indicators found, check URL for redirect
            if "/login" in page.url:
                logger.info("Authentication verification failed: redirected to login.")
                return False
            # As a fallback, assume valid if not redirected to login
            return True
        finally:
            await page.close()

    async def reauthenticate(self) -> bool:
        """Force a fresh login and replace any existing session.

        Returns:
            True if reauthentication succeeds.
        """
        logger.info("Re-authenticating (forcing fresh login)...")
        # Clear existing session file to prevent reuse of stale data
        if settings.storage_state_path.exists():
            settings.storage_state_path.unlink()
            logger.info("Cleared stale session file.")
        return await self.login()
