# Migrations (Supabase / PostgreSQL)

Run the SQL in **Supabase SQL Editor** or via `psql` using your database URL from `.env`.

## Run migration

**Option 1 – Supabase Dashboard**

1. Open [Supabase](https://supabase.com/dashboard) → your project → **SQL Editor**.
2. Paste the contents of `001_create_registrations.sql`.
3. Run the query.

**Option 2 – Command line**

```bash
# From project root, with .env loaded
set SUPABASE_DATABASE_URL=postgresql://postgres:...
psql "%SUPABASE_DATABASE_URL%" -f migrations/001_create_registrations.sql
```

On Linux/macOS:

```bash
export SUPABASE_DATABASE_URL="postgresql://..."
psql "$SUPABASE_DATABASE_URL" -f migrations/001_create_registrations.sql
```

## Files

- `001_create_registrations.sql` – Creates `public.registrations` table and indexes for MotoReg driver registrations.
