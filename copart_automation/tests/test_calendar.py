"""Tests for auction calendar parsing."""

from __future__ import annotations

import pytest

from copart_automation.app.calendar import AuctionCalendarParser
from copart_automation.app.models import AuctionCalendarEntry


class FakePage:
    def __init__(self, html: str) -> None:
        self._html = html

    async def content(self) -> str:
        return self._html


class TestAuctionCalendarParser:
    def test_normalize_date(self) -> None:
        parser = AuctionCalendarParser()
        assert parser._normalize_date("12/31/2025") == "2025-12-31"
        assert parser._normalize_date("December 31, 2025") == "December 31, 2025"

    def test_looks_like_time(self) -> None:
        parser = AuctionCalendarParser()
        assert parser._looks_like_time("10:30 AM") is True
        assert parser._looks_like_time("3:00pm") is True
        assert parser._looks_like_time("No time") is False

    @pytest.mark.asyncio
    async def test_parse_calendar(self) -> None:
        html = """
        <html>
          <body>
            <table class="auction-table">
              <tr>
                <th>Time</th>
                <th>03/15/2026</th>
                <th>03/16/2026</th>
              </tr>
              <tr>
                <td>10:00 AM</td>
                <td>Open Lot</td>
                <td>Closed Lot</td>
              </tr>
              <tr>
                <td>2:00 PM</td>
                <td>Inspection</td>
                <td></td>
              </tr>
            </table>
          </body>
        </html>
        """
        page = FakePage(html)
        parser = AuctionCalendarParser()
        entries = await parser.parse_calendar(page)

        assert len(entries) == 3
        assert entries[0].event_date == "2026-03-15"
        assert entries[0].auction_time == "10:00 AM"
        assert entries[0].description == "Open Lot"
        assert entries[1].event_date == "2026-03-16"
        assert entries[1].description == "Closed Lot"
        assert entries[2].event_date == "2026-03-15"
        assert entries[2].auction_time == "2:00 PM"
        assert entries[2].description == "Inspection"
