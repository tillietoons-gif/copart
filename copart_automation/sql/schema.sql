-- Copart Automation Database Schema
-- SQLite database for storing vehicle data, searches, and downloads.
-- This schema avoids duplicate records via unique constraints.

-- Enable foreign keys for referential integrity
PRAGMA foreign_keys = ON;

-- Vehicles: core data extracted from Copart listings
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vin TEXT NOT NULL,
    lot_number TEXT NOT NULL UNIQUE,
    title_text TEXT,
    year INTEGER,
    make TEXT,
    model TEXT,
    odometer INTEGER,
    damage_description TEXT,
    sale_date TEXT,
    current_bid REAL,
    auction_status TEXT,
    detail_url TEXT,
    image_urls TEXT,  -- Stored as JSON array string
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vin, lot_number)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_vehicles_vin ON vehicles(vin);
CREATE INDEX IF NOT EXISTS idx_vehicles_lot ON vehicles(lot_number);
CREATE INDEX IF NOT EXISTS idx_vehicles_make_model ON vehicles(make, model);
CREATE INDEX IF NOT EXISTS idx_vehicles_auction_status ON vehicles(auction_status);

-- Searches: audit trail of user-initiated search queries
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_type TEXT NOT NULL CHECK(query_type IN ('vin', 'lot', 'make', 'model', 'year', 'general')),
    query_value TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_searches_query_type ON searches(query_type);
CREATE INDEX IF NOT EXISTS idx_searches_executed_at ON searches(executed_at);

-- Downloads: tracking of downloaded files per vehicle/account
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT CHECK(file_type IN ('image', 'invoice', 'document', 'other')),
    download_url TEXT,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_size_bytes INTEGER,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    UNIQUE(vehicle_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_downloads_vehicle_id ON downloads(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_downloads_file_type ON downloads(file_type);

CREATE TABLE IF NOT EXISTS auction_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT NOT NULL,
    auction_time TEXT,
    description TEXT,
    table_section TEXT,
    row_index INTEGER,
    column_index INTEGER,
    lots_view_url TEXT,
    lots_view_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_date, auction_time, description)
);
CREATE INDEX IF NOT EXISTS idx_auction_calendar_lots_url ON auction_calendar(lots_view_url);
CREATE INDEX IF NOT EXISTS idx_auction_calendar_date ON auction_calendar(event_date);
CREATE INDEX IF NOT EXISTS idx_auction_calendar_section ON auction_calendar(table_section);

-- Trigger to update updated_at on vehicles updates
CREATE TRIGGER IF NOT EXISTS trg_vehicles_updated_at
AFTER UPDATE ON vehicles
FOR EACH ROW
BEGIN
    UPDATE vehicles SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
