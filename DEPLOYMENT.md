# Bahiran Delivery Driver Registration — Deployment Checklist

## ✅ Ready for deployment (after you complete the steps below)

### 1. **Environment variables (production)**
Set these on your server (e.g. in `.env` or your host’s env config). **Do not commit real keys to git.**

- `SUPABASE_URL` — Your Supabase project URL (e.g. `https://xxx.supabase.co`)
- `SUPABASE_ANON_KEY` or `SUPABASE_KEY` — Supabase anon/service key
- `SUPABASE_DATABASE_URL` or `DATABASE_URL` — PostgreSQL connection string (for registrations)
- `ADMIN_SECRET_KEY` — Strong random secret for Flask session signing (e.g. `openssl rand -hex 32`)
- `PORT` — Optional; default is 5050

### 2. **Database**
- Run migrations in order on your PostgreSQL/Supabase DB:
  - `001_create_registrations.sql`
  - `002_add_transport_type.sql`
  - `003_bike_optional_vehicle_fields.sql`
- Schema: `bahiran_driver.registrations`

### 3. **Supabase Storage**
- Create bucket `driver-documents` (or set `SUPABASE_STORAGE_BUCKET` to your bucket name).
- Ensure the anon key has storage upload/read permissions for that bucket.

### 4. **Admin credentials**
- `admin_users.json` is created on first run (default: username `admin`, PIN `4067`).
- **Change the default PIN** by editing `admin_users.json` and setting `pin_hash` to `sha256(your_new_pin)`.
- Or delete `admin_users.json` and restart to regenerate default; then change PIN as above.

### 5. **Production server**
Do **not** use Flask’s built-in server in production. Use a WSGI server, for example:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5050 "api.app:app"
```

Or with a reverse proxy (nginx/Apache) in front, binding to `127.0.0.1:5050` and proxying to it.

### 6. **HTTPS**
- Serve the app over HTTPS (e.g. nginx with SSL, or your host’s TLS).
- Set `SESSION_COOKIE_SECURE = True` in production if you use HTTPS (add in `api/app.py` when `DEBUG` is false or when a production env var is set).

### 7. **CORS**
- The app uses `flask-cors`. If the frontend is on a different domain, allow that origin in CORS config in `api/app.py`.

### 8. **Frontend API URL**
- Registration form uses **relative URLs** (e.g. `fetch('/register', ...)`), so it works as long as the same host serves both the HTML and the API.

---

## Quick pre-deploy check

| Item | Done |
|------|------|
| `.env` / env vars set (no secrets in repo) | |
| DB migrations run | |
| Supabase Storage bucket created and writable | |
| Default admin PIN changed | |
| `ADMIN_SECRET_KEY` set (production) | |
| Running with gunicorn (or similar), not `python run.py` | |
| HTTPS in production | |

---

_Last updated: deployment checklist for Bahiran Delivery Driver Registration._
