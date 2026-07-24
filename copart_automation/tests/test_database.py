"""Tests for database operations.

These tests use temporary SQLite databases to verify CRUD operations,
export functionality, and duplicate prevention without affecting
the production database.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from copart_automation.app.database import DatabaseModule
from copart_automation.app.models import SearchQuery, Vehicle




class TestDatabaseOperations:
    """Verify database module behavior with temporary files."""

    def test_database_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseModule(db_path=db_path)
            assert db_path.exists()

    def test_insert_and_retrieve_vehicle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseModule(db_path=db_path)
            vehicle = Vehicle(
                vin="TESTVIN1234567890",
                lot_number="TESTLOT001",
                year=2020,
                make="Toyota",
                model="Camry",
            )
            vehicle_id = db.insert_vehicle(vehicle)
            assert vehicle_id > 0

            retrieved = db.get_vehicle_by_lot("TESTLOT001")
            assert retrieved is not None
            assert retrieved.vin == "TESTVIN1234567890"

    def test_duplicate_prevention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseModule(db_path=db_path)
            vehicle = Vehicle(
                vin="TESTVIN1234567890",
                lot_number="TESTLOT002",
            )
            id1 = db.insert_vehicle(vehicle)
            id2 = db.insert_vehicle(vehicle)
            assert id1 == id2  # Should return existing record, not create new

    def test_insert_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseModule(db_path=db_path)
            query = SearchQuery(query_type="vin", query_value="TEST", result_count=1)
            query_id = db.insert_search(query)
            assert query_id > 0

    def test_export_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            export_path = Path(tmp) / "export.csv"
            db = DatabaseModule(db_path=db_path)
            vehicle = Vehicle(vin="TESTVIN1234567890", lot_number="EXPORT001")
            db.insert_vehicle(vehicle)
            result_path = db.export_to_csv(export_path)
            assert result_path.exists()

    def test_export_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            export_path = Path(tmp) / "export.json"
            db = DatabaseModule(db_path=db_path)
            vehicle = Vehicle(vin="TESTVIN1234567890", lot_number="EXPORT002")
            db.insert_vehicle(vehicle)
            result_path = db.export_to_json(export_path)
            assert result_path.exists()
