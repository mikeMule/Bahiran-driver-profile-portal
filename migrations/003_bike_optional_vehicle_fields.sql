-- =============================================================================
-- Migration 003: Allow NULL vehicle fields for Bike registrations
-- =============================================================================
-- When transport_type = 'bike', only basic info + ID card are collected.
-- Brand, year, plate, platecode, plateletter, platenum are not required for bike.
-- Run: psql "$SUPABASE_DATABASE_URL" -f migrations/003_bike_optional_vehicle_fields.sql
-- Or: Supabase SQL Editor → paste and run
-- =============================================================================

ALTER TABLE bahiran_driver.registrations
  ALTER COLUMN brand       DROP NOT NULL,
  ALTER COLUMN year        DROP NOT NULL,
  ALTER COLUMN plate       DROP NOT NULL,
  ALTER COLUMN platecode   DROP NOT NULL,
  ALTER COLUMN plateletter DROP NOT NULL,
  ALTER COLUMN platenum    DROP NOT NULL;

COMMENT ON COLUMN bahiran_driver.registrations.brand IS 'Vehicle brand; NULL for bike registrations';
COMMENT ON COLUMN bahiran_driver.registrations.year IS 'Manufacture year; NULL for bike';
COMMENT ON COLUMN bahiran_driver.registrations.plate IS 'Full plate (code-letters-num); NULL for bike';
COMMENT ON COLUMN bahiran_driver.registrations.platecode IS 'Region code; NULL for bike';
COMMENT ON COLUMN bahiran_driver.registrations.plateletter IS 'Plate letters; NULL for bike';
COMMENT ON COLUMN bahiran_driver.registrations.platenum IS 'Plate numbers; NULL for bike';
