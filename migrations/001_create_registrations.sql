-- Bahiran Delivery Driver Registration: driver registrations table for Supabase/PostgreSQL
-- Run this in Supabase SQL Editor or: psql $SUPABASE_DATABASE_URL -f migrations/001_create_registrations.sql

CREATE SCHEMA IF NOT EXISTS bahiran_driver;

-- Create table
CREATE TABLE IF NOT EXISTS bahiran_driver.registrations (
    id              TEXT PRIMARY KEY,
    ref             TEXT NOT NULL UNIQUE,
    firstname       TEXT NOT NULL,
    lastname        TEXT NOT NULL,
    fullname        TEXT NOT NULL,
    phone           TEXT NOT NULL,
    brand           TEXT NOT NULL,
    year            TEXT NOT NULL,
    plate           TEXT NOT NULL,
    platecode       TEXT NOT NULL,
    plateletter     TEXT NOT NULL,
    platenum        TEXT NOT NULL,
    licence_file    TEXT,
    idcard_file     TEXT,
    libre_file      TEXT,
    transport_type  TEXT NOT NULL DEFAULT 'motor',
    status          TEXT NOT NULL DEFAULT 'pending',
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_registrations_ref ON bahiran_driver.registrations (ref);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON bahiran_driver.registrations (status);
CREATE INDEX IF NOT EXISTS idx_registrations_registered_at ON bahiran_driver.registrations (registered_at DESC);
CREATE INDEX IF NOT EXISTS idx_registrations_phone ON bahiran_driver.registrations (phone);

-- Optional: RLS (Row Level Security) for Supabase – enable if using Supabase Auth
-- ALTER TABLE bahiran_driver.registrations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow anon read" ON bahiran_driver.registrations FOR SELECT USING (true);
-- CREATE POLICY "Allow anon insert" ON bahiran_driver.registrations FOR INSERT WITH CHECK (true);

-- Trigger to keep updated_at in sync
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

COMMENT ON TABLE bahiran_driver.registrations IS 'Bahiran Delivery Driver Registration motor driver registrations';

-- Grant permissions to the role used by the app (e.g. postgres from DATABASE_URL).
-- If your app uses a different role, run the same GRANTs for that role.
GRANT USAGE ON SCHEMA bahiran_driver TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON bahiran_driver.registrations TO postgres;
GRANT EXECUTE ON FUNCTION bahiran_driver.set_updated_at() TO postgres;
