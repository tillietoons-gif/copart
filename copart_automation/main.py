"""Main entry point for the Copart automation project.

Design decisions:
- The entry point uses an async context manager (`SessionManager`) to
  ensure that browser and session resources are always cleaned up,
  even when exceptions occur.
- The workflow demonstrates a safe pattern: initialize session,
  verify authentication, perform a search, parse results, and optionally
  download images. It does not attempt to interact with auction bidding.
- A short delay is included between major steps to respect server
  capacity and reduce the risk of rate limiting.
- MFA and additional verification are handled by pausing the workflow
  and prompting the user, rather than attempting automatic bypasses.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is available for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from copart_automation.app.auth import AuthManager
from copart_automation.app.browser import BrowserManager
from copart_automation.app.config import settings
from copart_automation.app.database import DatabaseModule
from copart_automation.app.downloader import DownloadManager
from copart_automation.app.logger import get_logger, setup_logging
from copart_automation.app.navigation import NavigationHelper
from copart_automation.app.search import SearchModule
from copart_automation.app.session import SessionManager
from copart_automation.app.calendar import AuctionCalendarParser

logger = get_logger(__name__)


async def run_automation_workflow() -> int:
    """Execute the standard automation workflow.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    setup_logging()
    logger.info("Starting Copart automation workflow")
    logger.info("Configuration: headless=%s, db=%s, download_dir=%s", settings.headless, settings.database_path, settings.download_dir)

    session_manager = SessionManager()
    try:
        async with session_manager:
            # Initialize and verify session
            logger.info("Initializing session...")
            await session_manager.verify_session(auto_reauth=True)

            # Create navigation helper using active session
            context = session_manager.browser.get_context()
            if not context:
                logger.error("No active browser context after session initialization.")
                return 1

            navigation = NavigationHelper(context)
            search_module = SearchModule(navigation)
            download_manager = DownloadManager(session_manager.browser)
            db = DatabaseModule()
            auction_parser = AuctionCalendarParser()

            # Scrape the auction calendar immediately after login
            logger.info("Navigating to auction calendar page...")
            calendar_page = await navigation.navigate_to_auction_calendar()
            try:
                calendar_entries = await auction_parser.parse_calendar(calendar_page)
                logger.info("Auction calendar parse returned %d entries", len(calendar_entries))
                for entry in calendar_entries:
                    db.insert_auction_calendar_entry(entry)
            finally:
                await calendar_page.close()

            # Example: navigate to dashboard to confirm session
            logger.info("Navigating to dashboard for confirmation...")
            page = await navigation.navigate_to_dashboard()
            await page.close()

            # Example: perform a search (use safe test values or user-configured values)
            # Note: This does not attempt to interact with bidding systems.
            # Real searches should be configured by the user via environment
            # or additional command-line arguments.
            test_vin = "5GZCZ43D13S812715"  # Example VIN for demonstration only
            logger.info("Performing example VIN search (demonstration): %s", test_vin)
            try:
                vehicles = await search_module.search_by_vin(test_vin)
                logger.info("Search returned %d vehicle(s)", len(vehicles))
                for vehicle in vehicles:
                    logger.info(
                        "Vehicle: %s | %s %s | Lot: %s | Bid: %s",
                        vehicle.vin,
                        vehicle.year,
                        vehicle.make,
                        vehicle.lot_number,
                        vehicle.current_bid,
                    )
                    # Persist to database
                    vehicle_id = db.insert_vehicle(vehicle)
                    # Optionally download images (limited for demonstration)
                    if vehicle.image_urls:
                        logger.info("Attempting to download images for lot %s", vehicle.lot_number)
                        try:
                            records = await download_manager.download_vehicle_images(vehicle, max_images=2)
                            for record in records:
                                # Update with actual database vehicle ID
                                if vehicle_id:
                                    record.vehicle_id = vehicle_id
                                db.insert_download(record)
                            logger.info("Downloaded %d images.", len(records))
                        except Exception as exc:
                            logger.warning(f"Image download failed (not blocking): {exc}")
            except Exception as exc:
                logger.warning(f"Search or parsing error (continuing): {exc}")

            # Example: export existing database to CSV
            try:
                export_path = settings.download_dir / "exports" / "vehicles.csv"
                db.export_to_csv(export_path)
            except Exception as exc:
                logger.warning(f"Export failed (not blocking): {exc}")

            # Graceful delay before closing to allow any pending downloads to finalize
            logger.info("Workflow complete. Waiting briefly for pending operations...")
            await asyncio.sleep(2)

        logger.info("Automation workflow completed successfully.")
        return 0
    except Exception as exc:
        logger.critical("Automation workflow failed: %s", exc, exc_info=True)
        return 1


def main() -> int:
    """Synchronous entry point that runs the async workflow.

    This allows the application to be called from standard Python scripts,
    command-line interfaces, or schedulers without requiring the caller
    to manage the event loop.
    """
    try:
        exit_code = asyncio.run(run_automation_workflow())
    except KeyboardInterrupt:
        logger.info("Workflow interrupted by user (SIGINT).")
        exit_code = 130
    except Exception as exc:
        logger.critical("Unhandled exception in main: %s", exc, exc_info=True)
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
