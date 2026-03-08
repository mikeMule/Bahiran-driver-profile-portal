-- =============================================================================
-- Bahiran Delivery Driver Registration / Bahiran Driver Profile Portal
-- Complete database schema: public.registrations
-- =============================================================================
-- Run: psql "$DATABASE_URL" -f migrations/000_complete_registrations_schema.sql
-- Or: Supabase SQL Editor → paste and run
-- =============================================================================

-- Schema
CREATE SCHEMA IF NOT EXISTS public;

-- -----------------------------------------------------------------------------
-- Table: public.registrations
-- Stores driver registrations for Car, Motor, and Bike. Bike requires only
-- ID card; Car/Motor require Driving licence, ID card, and Libre.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.registrations (
    -- Primary key & reference
    id              TEXT PRIMARY KEY,
    ref             TEXT NOT NULL UNIQUE,

    -- Personal
    firstname       TEXT NOT NULL,
    lastname        TEXT NOT NULL,
    fullname        TEXT NOT NULL,
    phone           TEXT NOT NULL,

    -- Vehicle (all types)
    transport_type  TEXT NOT NULL DEFAULT 'motor',  -- 'car' | 'motor' | 'bike'
    brand           TEXT NOT NULL,
    year            TEXT NOT NULL,
    plate           TEXT NOT NULL,
    platecode       TEXT NOT NULL,
    plateletter     TEXT NOT NULL,
    platenum        TEXT NOT NULL,

    -- Documents (licence/libre NULL for bike)
    licence_file    TEXT,
    idcard_file     TEXT,
    libre_file      TEXT,

    -- Status & timestamps
    status          TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Column comments
COMMENT ON TABLE public.registrations IS 'Bahiran Delivery Driver Registration driver registrations (Car, Motor, Bike)';
COMMENT ON COLUMN public.registrations.id IS 'Internal UUID/short id';
COMMENT ON COLUMN public.registrations.ref IS 'Display reference e.g. REF-A12B34';
COMMENT ON COLUMN public.registrations.transport_type IS 'car, motor, or bike';
COMMENT ON COLUMN public.registrations.licence_file IS 'Driving licence path; NULL for bike';
COMMENT ON COLUMN public.registrations.libre_file IS 'Libre/vehicle log path; NULL for bike';
COMMENT ON COLUMN public.registrations.status IS 'pending, approved, rejected';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_registrations_ref ON public.registrations (ref);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON public.registrations (status);
CREATE INDEX IF NOT EXISTS idx_registrations_registered_at ON public.registrations (registered_at DESC);
CREATE INDEX IF NOT EXISTS idx_registrations_phone ON public.registrations (phone);
CREATE INDEX IF NOT EXISTS idx_registrations_transport_type ON public.registrations (transport_type);

-- Trigger: auto-update updated_at
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_registrations_updated_at ON public.registrations;
CREATE TRIGGER trigger_registrations_updated_at
  BEFORE UPDATE ON public.registrations
  FOR EACH ROW
  EXECUTE PROCEDURE public.set_updated_at();

-- Permissions (adjust role if your app uses a different user)
GRANT USAGE ON SCHEMA public TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.registrations TO postgres;
GRANT EXECUTE ON FUNCTION public.set_updated_at() TO postgres;

-- =============================================================================
-- Optional: RLS for Supabase (uncomment if using Supabase Auth)
-- =============================================================================
-- ALTER TABLE public.registrations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow anon read" ON public.registrations FOR SELECT USING (true);
-- CREATE POLICY "Allow anon insert" ON public.registrations FOR INSERT WITH CHECK (true);
