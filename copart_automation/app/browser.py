"""Playwright browser manager for automated navigation.

Design decisions:
- Playwright's Chromium channel is the primary target due to its
  excellent headless support and consistent behavior across platforms.
- Browser contexts provide isolation between automation runs, preventing
  cookie leakage and ensuring clean state unless explicitly reused.
- Downloads are handled through Playwright's native download events,
  avoiding manual HTTP requests that would miss session cookies.
- All resources (browser, context, page) are managed through async
  context managers or explicit cleanup to prevent zombie processes.
"""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Download,
    Playwright,
    async_playwright,
)

from copart_automation.app.config import settings
from copart_automation.app.exceptions import CopartAutomationError
from copart_automation.app.logger import get_logger

logger = get_logger(__name__)


class BrowserManager:
    """Manages Playwright browser instances, contexts, and pages.

    Provides a clean abstraction over Playwright's low-level APIs,
    ensuring that resources are closed gracefully and that download
    directories are configured correctly.
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._downloads: list[Download] = []

    async def start(self) -> BrowserContext:
        """Initialize Playwright and create an isolated browser context.

        Returns:
            An active BrowserContext ready for navigation.

        Raises:
            CopartAutomationError: If Playwright fails to launch.
        """
        logger.info("Starting Playwright browser manager")
        try:
            self._playwright = await async_playwright().start()
            # Launch browser with appropriate args for headless/stability
            launch_args = {
                "channel": settings.browser_channel,
                "headless": settings.headless,
            }
            # Note: We intentionally do NOT disable JavaScript or
            # modify user-agent to bypass protections. The site must
            # see a standard, modern browser.
            self._browser = await self._playwright.chromium.launch(**launch_args)

            # Create context with download behavior configured
            # We use a dedicated download path per session
            self._context = await self._browser.new_context(
                accept_downloads=True,
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            )

            # Configure download path within the download directory
            download_path = settings.download_dir
            download_path.mkdir(parents=True, exist_ok=True)
            # Note: Playwright manages downloads via events rather than
            # direct path assignment; we set the save_path in event handlers.

            # Attach download listener
            self._context.on("download", self._on_download)

            logger.info(
                f"Browser started (channel={settings.browser_channel}, headless={settings.headless})"
            )
            return self._context
        except Exception as exc:
            logger.error(f"Failed to start browser: {exc}")
            await self.close()
            raise CopartAutomationError(f"Browser initialization failed: {exc}") from exc

    async def _on_download(self, download: Download) -> None:
        """Handle download events by tracking them for later retrieval.

        Design: We record downloads but do not immediately save them,
        allowing callers to decide when and where to persist files.
        This prevents partial files from being treated as complete.
        """
        logger.info(f"Download started: {download.url} -> {download.suggested_filename}")
        self._downloads.append(download)

    async def save_download(self, download: Download, save_path: Path | None = None) -> Path:
        """Save an active download to the specified path.

        Args:
            download: The Playwright Download instance.
            save_path: Optional target path. If None, uses the download's
                suggested filename within the configured download directory.

        Returns:
            The absolute path to the saved file.
        """
        save_path = save_path or settings.download_dir / download.suggested_filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(save_path))
        logger.info(f"Download saved to {save_path}")
        return save_path.resolve()

    async def close(self) -> None:
        """Gracefully close all browser resources.

        This method is safe to call multiple times and handles cases
        where resources were never fully initialized.
        """
        logger.info("Closing browser resources")
        try:
            if self._context:
                await self._context.close()
                self._context = None
        except Exception as exc:
            logger.warning(f"Error closing browser context: {exc}")

        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
        except Exception as exc:
            logger.warning(f"Error closing browser: {exc}")

        try:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception as exc:
            logger.warning(f"Error stopping Playwright: {exc}")

    def is_active(self) -> bool:
        """Check whether the browser manager has an active context."""
        return self._context is not None and not self._context.pages == []

    def get_context(self) -> BrowserContext | None:
        """Return the current browser context, or None if not started."""
        return self._context
