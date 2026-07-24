"""Pydantic data models for Copart automation.

Design decisions:
- All models use strict typing and validation to catch data errors early.
- Vehicle model uses optional fields for data that may not be available
  to all account tiers or listings.
- JSON serialization helpers are included for database and download tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Vehicle(BaseModel):
    """Structured representation of a Copart vehicle listing.

    All fields that may vary by account access are optional to prevent
    parsing failures when data is missing.
    """

    vin: str = Field(..., description="Vehicle Identification Number")
    lot_number: str = Field(..., description="Copart lot identifier")
    title_text: str | None = Field(default=None, description="Title status (e.g., Clean, Salvage)")
    year: int | None = Field(default=None, description="Model year", ge=1900, le=2100)
    make: str | None = Field(default=None, description="Manufacturer")
    model: str | None = Field(default=None, description="Model name")
    odometer: int | None = Field(default=None, description="Odometer reading in miles", ge=0)
    damage_description: str | None = Field(default=None, description="Primary damage notes")
    sale_date: str | None = Field(default=None, description="Auction sale date")
    current_bid: float | None = Field(default=None, description="Current bid amount", ge=0)
    auction_status: str | None = Field(default=None, description="Status (e.g., Live, Upcoming)")
    detail_url: HttpUrl | None = Field(default=None, description="Direct listing URL")
    image_urls: list[str] | None = Field(
        default=None, description="List of image URLs available to account"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    @field_validator("vin")
    @classmethod
    def vin_must_not_be_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("VIN cannot be empty")
        return cleaned

    @field_validator("lot_number")
    @classmethod
    def lot_must_not_be_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Lot number cannot be empty")
        return cleaned

    def to_database_dict(self) -> dict[str, Any]:
        """Convert model to a flat dictionary suitable for SQLite insertion.

        HttpUrl is converted to string; datetime objects are converted to
        ISO format strings for SQLite compatibility.
        """
        data = self.model_dump(mode="json", exclude_none=False)
        # Ensure datetime fields are strings for SQLite
        for key in ("created_at", "updated_at"):
            value = data.get(key)
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif value is not None:
                data[key] = str(value)
        # Convert image_urls list back to JSON string for DB storage if needed
        if isinstance(data.get("image_urls"), list):
            import json

            data["image_urls"] = json.dumps(data["image_urls"])
        if isinstance(data.get("detail_url"), str):
            data["detail_url"] = str(data["detail_url"])
        return data

    @classmethod
    def from_database_row(cls, row: dict[str, Any]) -> Vehicle:
        """Reconstruct a Vehicle instance from a SQLite result row.

        Handles JSON-encoded image_urls and string datetime values.
        """
        import json

        cleaned = dict(row)
        image_urls_raw = cleaned.get("image_urls")
        if isinstance(image_urls_raw, str):
            try:
                cleaned["image_urls"] = json.loads(image_urls_raw)
            except json.JSONDecodeError:
                cleaned["image_urls"] = None
        # Convert datetime strings back to datetime objects for Pydantic
        for key in ("created_at", "updated_at"):
            val = cleaned.get(key)
            if isinstance(val, str):
                from datetime import datetime

                try:
                    cleaned[key] = datetime.fromisoformat(val)
                except ValueError:
                    cleaned[key] = None
        return cls(**cleaned)


class SearchQuery(BaseModel):
    """Record of a user-initiated search within the automation."""

    query_type: str = Field(..., description="Search category (vin, lot, make, model, year, general)")
    query_value: str = Field(..., description="The search text or identifier")
    result_count: int = Field(default=0, ge=0, description="Number of results returned")
    executed_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(str_strip_whitespace=True)


class DownloadRecord(BaseModel):
    """Record of a downloaded file associated with a vehicle."""

    vehicle_id: int = Field(..., ge=1)
    file_path: str = Field(..., description="Absolute or relative file path")
    file_type: str | None = Field(
        default=None, description="Category: image, invoice, document, other"
    )
    download_url: str | None = Field(default=None)
    downloaded_at: datetime = Field(default_factory=datetime.utcnow)
    file_size_bytes: int | None = Field(default=None, ge=0)
