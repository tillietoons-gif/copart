"""Search functionality for Copart vehicle listings.

Design decisions:
- Search is performed through page interaction rather than direct API
  calls, ensuring that session cookies and anti-bot protections are
  respected.
- The module supports multiple search types but does not attempt to
  bypass rate limits. Delays between searches are the caller's
  responsibility (see main.py for example usage with delays).
"""

from __future__ import annotations

import time
from typing import Any

from playwright.async_api import Page

from copart_automation.app.navigation import NavigationHelper
from copart_automation.app.exceptions import NavigationError, ParseError
from copart_automation.app.logger import get_logger
from copart_automation.app.models import SearchQuery, Vehicle
from copart_automation.app.parser import VehicleParser

logger = get_logger(__name__)


class SearchModule:
    """Provides structured search capabilities against Copart listings.

    Search results are parsed and returned as structured Vehicle models.
    This module does not store results in the database; persistence is
    handled by the caller or DatabaseModule.
    """

    def __init__(self, navigation: NavigationHelper) -> None:
        self._navigation = navigation
        self._parser = VehicleParser()

    async def search_by_vin(self, vin: str, timeout: int = 30000) -> list[Vehicle]:
        """Search for vehicles by VIN.

        Args:
            vin: Vehicle Identification Number.
            timeout: Page interaction timeout.

        Returns:
            A list of Vehicle instances matching the VIN search.
        """
        logger.info("Starting VIN search for {}", vin)
        page = await self._navigation.navigate_to_search(timeout=timeout)
        try:
            # Interact with search form (selectors are approximate)
            await page.fill(
                "input[name='vin'], input#vin, input[type='text']",
                vin,
            )
            await page.click("button[type='submit'], input[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=timeout)
            vehicles = await self._parser.parse_search_results(page)
            logger.info("VIN search for {} returned {} results", vin, len(vehicles))
            return vehicles
        finally:
            await page.close()

    async def search_by_lot(self, lot_number: str, timeout: int = 30000) -> list[Vehicle]:
        """Search for a specific lot by lot number.

        Args:
            lot_number: The Copart lot identifier.
            timeout: Page interaction timeout.

        Returns:
            A list containing the matching vehicle (typically one result).
        """
        logger.info("Starting lot search for {}", lot_number)
        # Direct navigation to lot page is often faster than form search
        try:
            page = await self._navigation.navigate_to_vehicle(lot_number, timeout=timeout)
            vehicle = await self._parser.parse_vehicle_details(page)
            await page.close()
            if vehicle:
                return [vehicle]
            return []
        except NavigationError:
            logger.warning("Direct lot navigation failed; falling back to search form.")
            page = await self._navigation.navigate_to_search(timeout=timeout)
            try:
                await page.fill("input[name='lot'], input#lot", lot_number)
                await page.click("button[type='submit']")
                await page.wait_for_load_state("networkidle", timeout=timeout)
                vehicles = await self._parser.parse_search_results(page)
                return vehicles
            finally:
                await page.close()

    async def search_by_make_model(
        self, make: str, model: str | None = None, year: int | None = None, timeout: int = 30000
    ) -> list[Vehicle]:
        """Search by make, optional model, and optional year.

        Args:
            make: Vehicle manufacturer.
            model: Optional model name.
            year: Optional model year.
            timeout: Page interaction timeout.

        Returns:
            A list of Vehicle instances matching the criteria.
        """
        query_value = make
        if model:
            query_value += f" {model}"
        if year:
            query_value += f" {year}"
        logger.info("Starting make/model search: {}", query_value)
        page = await self._navigation.navigate_to_search(timeout=timeout)
        try:
            # Attempt to fill general search or specific fields
            await page.fill("input[type='text'], input[name='search']", query_value)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=timeout)
            vehicles = await self._parser.parse_search_results(page)
            logger.info("Make/model search returned {} results", len(vehicles))
            return vehicles
        finally:
            await page.close()

    async def search_by_year(self, year: int, timeout: int = 30000) -> list[Vehicle]:
        """Search for vehicles by model year.

        Args:
            year: The model year to search for.
            timeout: Page interaction timeout.

        Returns:
            A list of Vehicle instances for the specified year.
        """
        return await self.search_by_make_model("", year=year, timeout=timeout)
