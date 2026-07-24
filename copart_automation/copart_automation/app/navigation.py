"""Reusable navigation helpers for common Copart pages.

Design decisions:
- Navigation is abstracted away from raw Playwright calls to provide
  a semantic interface (e.g., `go_to_search()` instead of `goto(...)`).
- Each navigation method verifies the target page by checking the URL
  or a known element, providing early failure detection.
- Navigation errors raise `NavigationError` with descriptive messages
  rather than propagating raw Playwright exceptions.
"""

from __future__ import annotations

from playwright.async_api import BrowserContext, Page

from copart_automation.app.config import settings
from copart_automation.app.exceptions import NavigationError
from copart_automation.app.logger import get_logger

logger = get_logger(__name__)

# Common Copart navigation endpoints (approximate; adjust based on site updates)
NAVIGATION_PATHS = {
    "dashboard": "/",
    "search": "/search",
    "purchases": "/purchases",
    "auctions": "/auctions",
    "invoices": "/invoices",
    "auctionCalendar": "/auctionCalendar",
}


class NavigationHelper:
    """Provides semantic navigation to common Copart account pages.

    Requires an active BrowserContext (typically from an initialized
    SessionManager) to function.
    """

    def __init__(self, context: BrowserContext) -> None:
        self._context = context
        if self._context is None:
            raise NavigationError("Navigation requires an active browser context.")

    async def navigate_to_page(
        self,
        page_name: str,
        timeout: int = 30000,
        wait_until: str = "networkidle",
    ) -> Page:
        """Navigate to a named page and return the active Page instance.

        Args:
            page_name: Key from NAVIGATION_PATHS or a full URL.
            timeout: Navigation timeout in milliseconds.
            wait_until: Playwright load state to wait for.

        Returns:
            The Playwright Page instance after successful navigation.
        """
        url = NAVIGATION_PATHS.get(page_name, page_name)
        if not url.startswith("http"):
            url = f"https://www.copart.com{url}"

        logger.info("Navigating to {} ({})", page_name, url)
        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=timeout, wait_until=wait_until)
            # Verify navigation success
            current_url = page.url
            if "/login" in current_url or "/signin" in current_url:
                raise NavigationError(
                    f"Navigation to '{page_name}' redirected to login. Session may have expired."
                )
            logger.info("Successfully navigated to {} (current URL: {})", page_name, current_url)
            return page
        except NavigationError:
            raise
        except Exception as exc:
            logger.error(f"Failed to navigate to {page_name}: {exc}")
            await page.close()
            raise NavigationError(f"Failed to navigate to '{page_name}': {exc}") from exc

    async def navigate_to_dashboard(self, timeout: int = 30000) -> Page:
        return await self.navigate_to_page("dashboard", timeout=timeout)

    async def navigate_to_search(self, timeout: int = 30000) -> Page:
        return await self.navigate_to_page("search", timeout=timeout)

    async def navigate_to_purchases(self, timeout: int = 30000) -> Page:
        return await self.navigate_to_page("purchases", timeout=timeout)

    async def navigate_to_auctions(self, timeout: int = 30000) -> Page:
        return await self.navigate_to_page("auctions", timeout=timeout)

    async def navigate_to_invoices(self, timeout: int = 30000) -> Page:
        return await self.navigate_to_page("invoices", timeout=timeout)

    async def navigate_to_auction_calendar(self, timeout: int = 30000) -> Page:
        return await self.navigate_to_page("auctionCalendar", timeout=timeout)

    async def navigate_to_vehicle(self, lot_number: str, timeout: int = 30000) -> Page:
        """Navigate to a specific vehicle detail page by lot number.

        Args:
            lot_number: The Copart lot identifier.
            timeout: Navigation timeout in milliseconds.

        Returns:
            The Page instance for the vehicle detail page.
        """
        url = f"https://www.copart.com/lot/{lot_number}"
        logger.info("Navigating to vehicle detail page: %s", url)
        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=timeout, wait_until="networkidle")
            if "/login" in page.url:
                raise NavigationError(f"Vehicle page redirected to login for lot {lot_number}.")
            return page
        except NavigationError:
            raise
        except Exception as exc:
            logger.error(f"Failed to navigate to vehicle {lot_number}: {exc}")
            await page.close()
            raise NavigationError(
                f"Failed to navigate to vehicle lot {lot_number}: {exc}"
            ) from exc
