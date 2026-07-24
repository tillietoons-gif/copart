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

    @pytest.mark.asyncio
    async def test_parse_calendar_with_view_lots_links(self) -> None:
        html = """
        <html><body>
          <table class="auction-table">
            <tr><th>Time</th><th>03/15/2026</th><th>03/16/2026</th></tr>
            <tr><td>10:00 AM</td><td>Open Lot <a href="/auction/123">View Lots</a></td><td>Closed Lot <a href="https://www.copart.com/lot/search?saleId=456">View Auction</a></td></tr>
            <tr><td>2:00 PM</td><td>Inspection <a href="/search?auction=789">View Inventory</a></td><td></td></tr>
          </table>
        </body></html>
        """
        page = FakePage(html)
        parser = AuctionCalendarParser()
        entries = await parser.parse_calendar(page)

        assert len(entries) == 3
        assert entries[0].lots_view_url is not None
        assert "https://www.copart.com/auction/123" in str(entries[0].lots_view_url)
        assert entries[0].lots_view_text is not None and "View Lots" in entries[0].lots_view_text
        assert "456" in str(entries[1].lots_view_url)
        assert "789" in str(entries[2].lots_view_url)

    @pytest.mark.asyncio
    async def test_parse_calendar_row_level_button(self) -> None:
        html = """
        <html><body>
          <table>
            <tr><th>Time</th><th>03/15/2026</th><th>Action</th></tr>
            <tr><td>10:00 AM</td><td>Open Lot</td><td><a href="/auction/row123" class="btn">View Lots</a></td></tr>
            <tr><td>2:00 PM</td><td>Inspection</td><td><button data-url="/auction/row456">View Lots</button></td></tr>
          </table>
        </body></html>
        """
        page = FakePage(html)
        parser = AuctionCalendarParser()
        entries = await parser.parse_calendar(page)

        assert len(entries) == 2
        assert any("row123" in str(e.lots_view_url) for e in entries)
        assert any("row456" in str(e.lots_view_url) for e in entries)

    @pytest.mark.asyncio
    async def test_parse_calendar_list_style_with_links(self) -> None:
        html = """
        <html><body>
          <table>
            <tr><th>Date</th><th>Time</th><th>Location</th><th>Sale Name</th><th>Action</th></tr>
            <tr><td>03/15/2026</td><td>10:00 AM</td><td>Miami</td><td>Dealer Sale</td><td><a href="/auction/miami123">View Lots</a></td></tr>
            <tr><td>03/16/2026</td><td>2:00 PM</td><td>Los Angeles</td><td>Live Auction</td><td><a href="https://www.copart.com/search?sale=la456">View Auction</a></td></tr>
            <tr><td>03/17/2026</td><td>9:00 AM</td><td>Chicago</td><td>Salvage Sale</td><td><button onclick="window.location='/sale/chicago789'">View Inventory</button></td></tr>
          </table>
        </body></html>
        """
        page = FakePage(html)
        parser = AuctionCalendarParser()
        entries = await parser.parse_calendar(page)

        assert len(entries) == 3
        assert entries[0].event_date == "2026-03-15"
        assert "miami123" in str(entries[0].lots_view_url)
        assert "la456" in str(entries[1].lots_view_url)
        assert "chicago789" in str(entries[2].lots_view_url)

    def test_normalize_url(self) -> None:
        parser = AuctionCalendarParser()
        assert parser._normalize_url("/auction/123") == "https://www.copart.com/auction/123"
        assert parser._normalize_url("https://www.copart.com/auction/123") == "https://www.copart.com/auction/123"
        assert parser._normalize_url("//www.copart.com/auction/123") == "https://www.copart.com/auction/123"
        assert parser._normalize_url("#") is None
        assert parser._normalize_url("javascript:void(0)") is None
