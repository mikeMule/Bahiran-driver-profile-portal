-- =============================================================================
-- Bahiran Delivery Driver Registration — FINAL migration (fresh install)
-- =============================================================================
-- Single script: schema + table + indexes + trigger + comments + grants.
-- Vehicle fields (brand, year, plate, etc.) are nullable for Bicycles.
-- Run: psql "$SUPABASE_DATABASE_URL" -f migrations/final001.sql
-- Or: Supabase SQL Editor → paste and run
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bahiran_driver;

-- -----------------------------------------------------------------------------
-- Table: bahiran_driver.registrations
-- Car/Motor: full vehicle + documents. Bicycles: personal + ID card only.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bahiran_driver.registrations (
    id              TEXT PRIMARY KEY,
    ref             TEXT NOT NULL UNIQUE,
    firstname       TEXT NOT NULL,
    lastname        TEXT NOT NULL,
    fullname        TEXT NOT NULL,
    phone           TEXT NOT NULL,
    transport_type  TEXT NOT NULL DEFAULT 'motor',
    brand           TEXT,
    year            TEXT,
    plate           TEXT,
    platecode       TEXT,
    plateletter     TEXT,
    platenum        TEXT,
    licence_file    TEXT,
    idcard_file     TEXT,
    libre_file      TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_registrations_ref ON bahiran_driver.registrations (ref);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON bahiran_driver.registrations (status);
CREATE INDEX IF NOT EXISTS idx_registrations_registered_at ON bahiran_driver.registrations (registered_at DESC);
CREATE INDEX IF NOT EXISTS idx_registrations_phone ON bahiran_driver.registrations (phone);
CREATE INDEX IF NOT EXISTS idx_registrations_transport_type ON bahiran_driver.registrations (transport_type);

-- Trigger: auto-update updated_at
CREATE OR REPLACE FUNCTION bahiran_driver.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_registrations_updated_at ON bahiran_driver.registrations;
CREATE TRIGGER trigger_registrations_updated_at
  BEFORE UPDATE ON bahiran_driver.registrations
  FOR EACH ROW
  EXECUTE PROCEDURE bahiran_driver.set_updated_at();

-- Comments
COMMENT ON TABLE bahiran_driver.registrations IS 'Bahiran Delivery Driver Registration (Car, Motor, Bicycles)';
COMMENT ON COLUMN bahiran_driver.registrations.transport_type IS 'car, motor, or bike';
COMMENT ON COLUMN bahiran_driver.registrations.brand IS 'Vehicle brand; NULL for Bicycles';
COMMENT ON COLUMN bahiran_driver.registrations.year IS 'Manufacture year; NULL for Bicycles';
COMMENT ON COLUMN bahiran_driver.registrations.plate IS 'Full plate; NULL for Bicycles';
COMMENT ON COLUMN bahiran_driver.registrations.licence_file IS 'Driving licence path; NULL for Bicycles';
COMMENT ON COLUMN bahiran_driver.registrations.libre_file IS 'Libre path; NULL for Bicycles';
COMMENT ON COLUMN bahiran_driver.registrations.status IS 'pending, approved, rejected';

-- Permissions
GRANT USAGE ON SCHEMA bahiran_driver TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON bahiran_driver.registrations TO postgres;
GRANT EXECUTE ON FUNCTION bahiran_driver.set_updated_at() TO postgres;

-- =============================================================================
-- Optional: RLS for Supabase (uncomment if using Supabase Auth)
-- =============================================================================
-- ALTER TABLE bahiran_driver.registrations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow anon read" ON bahiran_driver.registrations FOR SELECT USING (true);
-- CREATE POLICY "Allow anon insert" ON bahiran_driver.registrations FOR INSERT WITH CHECK (true);
