-- Add transport_type for existing DBs (car, motor, bike). New installs get it from 001.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'bahiran_driver' AND table_name = 'registrations' AND column_name = 'transport_type'
  ) THEN
    ALTER TABLE bahiran_driver.registrations ADD COLUMN transport_type TEXT NOT NULL DEFAULT 'motor';
  END IF;
END $$;
