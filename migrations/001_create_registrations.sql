-- MotoReg Ethiopia: driver registrations table for Supabase/PostgreSQL
-- Run this in Supabase SQL Editor or: psql $SUPABASE_DATABASE_URL -f migrations/001_create_registrations.sql

-- Create table
CREATE TABLE IF NOT EXISTS public.registrations (
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
    status          TEXT NOT NULL DEFAULT 'pending',
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_registrations_ref ON public.registrations (ref);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON public.registrations (status);
CREATE INDEX IF NOT EXISTS idx_registrations_registered_at ON public.registrations (registered_at DESC);
CREATE INDEX IF NOT EXISTS idx_registrations_phone ON public.registrations (phone);

-- Optional: RLS (Row Level Security) for Supabase – enable if using Supabase Auth
-- ALTER TABLE public.registrations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow anon read" ON public.registrations FOR SELECT USING (true);
-- CREATE POLICY "Allow anon insert" ON public.registrations FOR INSERT WITH CHECK (true);

-- Trigger to keep updated_at in sync
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

COMMENT ON TABLE public.registrations IS 'MotoReg Ethiopia motor driver registrations';
