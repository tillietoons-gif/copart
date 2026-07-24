"""Tests for Pydantic data models.

These tests verify validation, serialization, and database conversion
for Vehicle, SearchQuery, and DownloadRecord models.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from copart_automation.app.models import DownloadRecord, SearchQuery, Vehicle


class TestVehicleModel:
    """Verify Vehicle validation and conversion."""

    def test_valid_vehicle(self) -> None:
        """A fully populated Vehicle should validate successfully."""
        vehicle = Vehicle(
            vin="5GZCZ43D13S812715",
            lot_number="12345678",
            year=2013,
            make="Chevrolet",
            model="Malibu",
            current_bid=2500.0,
        )
        assert vehicle.vin == "5GZCZ43D13S812715"
        assert vehicle.lot_number == "12345678"
        assert vehicle.current_bid == 2500.0

    def test_missing_vin_fails(self) -> None:
        """A vehicle without VIN should fail validation."""
        with pytest.raises(ValidationError):
            Vehicle(lot_number="123")

    def test_empty_lot_fails(self) -> None:
        """A vehicle with an empty lot number should fail validation."""
        with pytest.raises(ValidationError):
            Vehicle(vin="TESTVIN1234567890", lot_number="   ")

    def test_to_database_dict(self) -> None:
        """Database dictionary should contain string representations."""
        vehicle = Vehicle(vin="TESTVIN1234567890", lot_number="123")
        data = vehicle.to_database_dict()
        assert isinstance(data["vin"], str)
        assert isinstance(data["lot_number"], str)

    def test_from_database_row(self) -> None:
        """Reconstruction from a database row should preserve data."""
        row = {
            "vin": "TESTVIN1234567890",
            "lot_number": "123",
            "year": 2020,
            "current_bid": 1500.0,
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:00:00",
            "image_urls": '["https://example.com/img.jpg"]',
        }
        vehicle = Vehicle.from_database_row(row)
        assert vehicle.vin == "TESTVIN1234567890"
        assert vehicle.image_urls == ["https://example.com/img.jpg"]

    def test_invalid_year_rejected(self) -> None:
        """Years outside the valid range should be rejected."""
        with pytest.raises(ValidationError):
            Vehicle(vin="TESTVIN1234567890", lot_number="123", year=1899)


class TestSearchQueryModel:
    """Verify SearchQuery behavior."""

    def test_search_query_creation(self) -> None:
        query = SearchQuery(query_type="vin", query_value="TESTVIN1234567890", result_count=1)
        assert query.query_type == "vin"
        assert query.result_count == 1


class TestDownloadRecord:
    """Verify DownloadRecord behavior."""

    def test_download_record(self) -> None:
        record = DownloadRecord(
            vehicle_id=42,
            file_path="/downloads/test.jpg",
            file_type="image",
            file_size_bytes=1024,
        )
        assert record.vehicle_id == 42
        assert record.file_type == "image"
