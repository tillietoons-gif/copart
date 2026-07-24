"""Auction calendar scraping for Copart automation.

This module scrapes the Copart auction calendar page after authentication
and converts calendar tables into structured entries for database storage.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import Page

from copart_automation.app.logger import get_logger
from copart_automation.app.models import AuctionCalendarEntry

logger = get_logger(__name__)


class AuctionCalendarParser:
    """Parses Copart auction calendar pages into structured calendar entries."""

    async def parse_calendar(self, page: Page) -> list[AuctionCalendarEntry]:
        """Parse the auction calendar from the given page."""
        page_url = getattr(page, "url", "unknown")
        logger.info("Parsing auction calendar from {}", page_url)
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "lxml")

        table_selectors = ["table.auction-table", "table"]
        tables = []
        for selector in table_selectors:
            tables.extend(soup.select(selector))
            if tables:
                break

        entries: list[AuctionCalendarEntry] = []
        for table_index, table in enumerate(tables, start=1):
            entries.extend(self._parse_calendar_table(table, table_index))

        logger.info("Parsed {} auction calendar entries", len(entries))
        return entries

    def _parse_calendar_table(self, table: Any, table_index: int) -> list[AuctionCalendarEntry]:
        rows = table.select("tr")
        if not rows:
            return []

        headers = self._extract_headers(rows[0])
        if not headers:
            return []

        entries: list[AuctionCalendarEntry] = []
        for row_index, row in enumerate(rows[1:], start=1):
            cells = row.select("td, th")
            if len(cells) < 2:
                continue

            auction_time = self._clean_cell_text(cells[0])
            if not self._looks_like_time(auction_time):
                # Skip rows that appear to be repeated header rows or non-event labels
                if self._looks_like_date(auction_time):
                    continue

            for column_index, cell in enumerate(cells[1:], start=1):
                description = self._clean_cell_text(cell)
                if not description:
                    continue

                event_date = headers[column_index - 1] if column_index - 1 < len(headers) else ""
                if not event_date:
                    continue

                entries.append(
                    AuctionCalendarEntry(
                        event_date=event_date,
                        auction_time=auction_time if self._looks_like_time(auction_time) else None,
                        description=description,
                        table_section=f"table-{table_index}",
                        row_index=row_index,
                        column_index=column_index,
                    )
                )
        return entries

    def _extract_headers(self, header_row: Any) -> list[str]:
        headers: list[str] = []
        cells = header_row.select("td, th")[1:]
        for cell in cells:
            text = self._clean_cell_text(cell)
            date_value = self._normalize_date(text)
            if date_value:
                headers.append(date_value)
            elif text:
                headers.append(text)
        return headers

    @staticmethod
    def _clean_cell_text(cell: Any) -> str:
        if not cell:
            return ""
        text = cell.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_date(text: str) -> str:
        if not text:
            return ""
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if match:
            month, day, year = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return text

    @staticmethod
    def _looks_like_time(text: str) -> bool:
        return bool(re.search(r"\b\d{1,2}:\d{2}\s*(AM|PM|am|pm)\b", text))

    @staticmethod
    def _looks_like_date(text: str) -> bool:
        return bool(re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text))
