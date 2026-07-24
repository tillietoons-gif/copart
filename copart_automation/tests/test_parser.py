"""Tests for parsing helpers and utilities.

These tests verify that the VehicleParser's cleaning and extraction
methods behave correctly without requiring a real browser session.
"""

from __future__ import annotations

import pytest

from copart_automation.app.parser import VehicleParser


class _FakeResponse:
    def __init__(self, payload: str, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    async def text(self) -> str:
        return self._payload


class _FakeRequest:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
        return _FakeResponse(self.payload)


class _FakePage:
    def __init__(self, payload: str) -> None:
        self.url = "https://www.copart.com/saleListResult/23/2026-07-24"
        self.request = _FakeRequest(payload)

    async def evaluate(self, script: str) -> str:
        return self.request.payload

    async def content(self) -> str:
        return self.request.payload


class TestParserHelpers:
    """Verify static parser utility methods."""

    def test_clean_vin_valid(self) -> None:
        assert VehicleParser._clean_vin("5GZCZ43D13S812715") == "5GZCZ43D13S812715"
        assert VehicleParser._clean_vin("VIN: 5GZCZ43D13S812715") == "5GZCZ43D13S812715"

    def test_clean_vin_invalid(self) -> None:
        assert VehicleParser._clean_vin("NOTAVIN") is None
        assert VehicleParser._clean_vin("") is None

    def test_clean_lot_valid(self) -> None:
        assert VehicleParser._clean_lot("12345678") == "12345678"
        assert VehicleParser._clean_lot("Lot: 12345678") == "12345678"

    def test_clean_int_valid(self) -> None:
        assert VehicleParser._clean_int("2020") == 2020
        assert VehicleParser._clean_int("Mileage: 45000 miles") == 45000

    def test_clean_float_valid(self) -> None:
        assert VehicleParser._clean_float("$2,500.00") == 2500.0
        assert VehicleParser._clean_float("1500") == 1500.0

    def test_find_text(self) -> None:
        from bs4 import BeautifulSoup
        html = '<div><span class="vin">TESTVIN1234567890</span></div>'
        soup = BeautifulSoup(html, "lxml")
        result = VehicleParser._find_text(soup, [".vin"])
        assert result == "TESTVIN1234567890"

    def test_find_text_missing(self) -> None:
        from bs4 import BeautifulSoup
        html = '<div></div>'
        soup = BeautifulSoup(html, "lxml")
        result = VehicleParser._find_text(soup, [".missing"])
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_export_lot_search_results(self) -> None:
        parser = VehicleParser()
        page = _FakePage(
            '[{"lotNumber":"12345678","vin":"5GZCZ43D13S812715","title":"Clean","year":"2020","make":"Chevrolet","model":"Camaro","odometer":"45000","damage":"Front End","currentBid":"2500.00"}]'
        )

        vehicles = await parser.parse_export_lot_search_results(page)

        assert len(vehicles) == 1
        assert vehicles[0].lot_number == "12345678"
        assert vehicles[0].vin == "5GZCZ43D13S812715"
        assert vehicles[0].make == "Chevrolet"
        assert vehicles[0].current_bid == 2500.0
