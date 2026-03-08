-- =============================================================================
-- Bahiran Delivery Driver Registration — FINAL migration (fresh install)
-- =============================================================================
-- Single script: schema + table + indexes + trigger + comments + grants.
-- Vehicle fields (brand, year, plate, etc.) are nullable for Bicycles.
-- Run: psql "$SUPABASE_DATABASE_URL" -f migrations/final001.sql
-- Or: Supabase SQL Editor → paste and run
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS public;

-- -----------------------------------------------------------------------------
-- Table: public.registrations
-- Car/Motor: full vehicle + documents. Bicycles: personal + ID card only.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.registrations (
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

-- Comments
COMMENT ON TABLE public.registrations IS 'Bahiran Delivery Driver Registration (Car, Motor, Bicycles)';
COMMENT ON COLUMN public.registrations.transport_type IS 'car, motor, or bike';
COMMENT ON COLUMN public.registrations.brand IS 'Vehicle brand; NULL for Bicycles';
COMMENT ON COLUMN public.registrations.year IS 'Manufacture year; NULL for Bicycles';
COMMENT ON COLUMN public.registrations.plate IS 'Full plate; NULL for Bicycles';
COMMENT ON COLUMN public.registrations.licence_file IS 'Driving licence path; NULL for Bicycles';
COMMENT ON COLUMN public.registrations.libre_file IS 'Libre path; NULL for Bicycles';
COMMENT ON COLUMN public.registrations.status IS 'pending, approved, rejected';

-- Permissions
GRANT USAGE ON SCHEMA public TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.registrations TO postgres;
GRANT EXECUTE ON FUNCTION public.set_updated_at() TO postgres;

-- =============================================================================
-- Optional: RLS for Supabase (uncomment if using Supabase Auth)
-- =============================================================================
-- ALTER TABLE public.registrations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow anon read" ON public.registrations FOR SELECT USING (true);
-- CREATE POLICY "Allow anon insert" ON public.registrations FOR INSERT WITH CHECK (true);
