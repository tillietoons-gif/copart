"""Download manager for account-accessible files.

Design decisions:
- Downloads are handled through Playwright's native download events,
  ensuring that session cookies and authentication headers are preserved.
- Files are organized into per-vehicle folders using safe filenames
  derived from the vehicle lot number and original file name.
- The download manager tracks file sizes and download URLs for auditing.
- This module does not bypass access controls; it only downloads files
  that are accessible through the authenticated browser session.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page

from copart_automation.app.browser import BrowserManager
from copart_automation.app.config import settings
from copart_automation.app.exceptions import DownloadError
from copart_automation.app.logger import get_logger
from copart_automation.app.models import DownloadRecord, Vehicle

logger = get_logger(__name__)


class DownloadManager:
    """Manages file downloads through the authenticated browser session.

    Downloads images, invoices, and other account-accessible documents,
    organizing them into structured folders.
    """

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._manager = browser_manager

    async def download_file(
        self,
        url: str,
        save_path: Path,
        timeout: int = 60000,
    ) -> Path:
        """Download a single file by navigating to its URL.

        Args:
            url: The direct download URL.
            save_path: The target file path.
            timeout: Maximum time to wait for the download event.

        Returns:
            The absolute path to the saved file.

        Raises:
            DownloadError: If the download fails or the file is inaccessible.
        """
        context = self._manager.get_context()
        if not context:
            raise DownloadError("No active browser context for download.")

        save_path.parent.mkdir(parents=True, exist_ok=True)
        page = await context.new_page()
        try:
            logger.info("Starting download from {}", url)
            # Set up download event tracking
            download_started = False
            download_complete = False
            download_path = None

            async def handle_download(download) -> None:
                nonlocal download_started, download_complete, download_path
                download_started = True
                download_path = await self._manager.save_download(
                    download, save_path
                )
                download_complete = True

            context.on("download", handle_download)

            # Navigate to URL; some downloads trigger via direct URL access
            await page.goto(url, timeout=timeout, wait_until="networkidle")

            # Wait for download event
            for _ in range(int(timeout / 1000)):
                if download_complete:
                    break
                await page.wait_for_timeout(1000)

            if not download_started:
                # If no download event occurred, check if the page itself
                # contains downloadable content or is a direct file.
                content_type = await page.evaluate("() => document.contentType")
                if content_type and ("pdf" in content_type or "image" in content_type):
                    # Save the page content directly as a fallback
                    content = await page.content()
                    with open(save_path, "wb") as f:
                        f.write(content.encode("utf-8"))
                    download_path = save_path.resolve()
                    download_complete = True
                else:
                    raise DownloadError(
                        f"Download event did not trigger for URL: {url}"
                    )

            if not download_complete:
                raise DownloadError(f"Download timed out for URL: {url}")

            # Verify file exists
            if not download_path.exists():
                raise DownloadError(f"Download file missing after save: {download_path}")

            file_size = download_path.stat().st_size
            logger.info("Download complete: {} ({} bytes)", download_path, file_size)
            return download_path
        except Exception as exc:
            if isinstance(exc, DownloadError):
                raise
            logger.error(f"Download failed: {exc}")
            raise DownloadError(f"Failed to download from {url}: {exc}") from exc
        finally:
            await page.close()

    async def download_vehicle_images(
        self,
        vehicle: Vehicle,
        max_images: int = 5,
    ) -> list[DownloadRecord]:
        """Download images for a vehicle organized into per-vehicle folders.

        Args:
            vehicle: The Vehicle instance with image_urls.
            max_images: Maximum number of images to download.

        Returns:
            A list of DownloadRecord instances for each downloaded file.
        """
        if not vehicle.image_urls:
            logger.info("No image URLs available for vehicle {}", vehicle.lot_number)
            return []

        base_folder = settings.download_dir / "vehicles" / str(vehicle.lot_number)
        base_folder.mkdir(parents=True, exist_ok=True)
        records: list[DownloadRecord] = []

        for idx, url in enumerate(vehicle.image_urls[:max_images]):
            # Derive safe filename from URL
            filename = Path(url.split("/")[-1] or f"image_{idx}.jpg")
            # Sanitize filename
            safe_filename = self._sanitize_filename(str(filename))
            save_path = base_folder / safe_filename

            try:
                await self.download_file(url, save_path)
                record = DownloadRecord(
                    vehicle_id=0,
                    file_path=str(save_path.resolve()),
                    file_type="image",
                    download_url=url,
                    file_size_bytes=save_path.stat().st_size,
                )
                records.append(record)
            except DownloadError as exc:
                logger.warning(f"Failed to download image {url}: {exc}")
                # Continue with remaining images
                continue

        return records

    async def download_invoice(
        self,
        invoice_url: str,
        lot_number: str,
        save_path: Path | None = None,
    ) -> DownloadRecord:
        """Download an invoice document for a specific lot.

        Args:
            invoice_url: Direct URL to the invoice file.
            lot_number: The lot identifier for folder organization.
            save_path: Optional explicit save path.

        Returns:
            A DownloadRecord describing the downloaded file.
        """
        folder = settings.download_dir / "invoices" / str(lot_number)
        folder.mkdir(parents=True, exist_ok=True)
        if save_path is None:
            save_path = folder / "invoice.pdf"

        path = await self.download_file(invoice_url, save_path)
        return DownloadRecord(
            vehicle_id=0,  # Caller should update with actual vehicle ID
            file_path=str(path.resolve()),
            file_type="invoice",
            download_url=invoice_url,
            file_size_bytes=path.stat().st_size,
        )

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize a filename to prevent filesystem issues.

        Removes or replaces characters that are invalid on common
        filesystems and limits the overall length.
        """
        import re

        # Replace invalid characters
        sanitized = re.sub(r"[<>:\"/\\|?*]", "_", name)
        # Limit length
        if len(sanitized) > 200:
            sanitized = sanitized[:200]
        # Ensure non-empty
        if not sanitized or sanitized == ".":
            sanitized = "download"
        return sanitized
