# GebetaDev Team - [MICHAEL] — Bahiran Delivery Driver Registration Driver Profile Portal

**Project:** Production-ready driver registration and admin portal (Flask API + static frontend).  
**Codebase:** Clean folder structure, API in `api/`, minimal and commented.

---

## Folder structure

```
Bahiran-driver-profile-portal/
├── api/                          # Backend API (all server logic)
│   ├── __init__.py               # Exposes app for run.py
│   └── app.py                    # Flask app: routes, DB, Supabase, admin, file serving
├── migrations/                   # SQL migrations (PostgreSQL / Supabase)
│   ├── 000_complete_registrations_schema.sql
│   ├── 001_create_registrations.sql
│   └── 002_add_transport_type.sql
├── css/                          # Styles (register.css; index.html can inline)
├── admin/                        # Alternate admin HTML (optional)
├── assets/                       # Static assets (e.g. logo.png)
├── uploads/                      # Local uploads (created at runtime; gitignored)
├── run.py                        # Entry point: python run.py
├── server.py                     # Backward-compat launcher → api.app
├── index.html                 # Registration frontend (CSS can be inlined)
├── admin.html                    # Admin panel frontend
├── .env.example                  # Example env vars (copy to .env)
├── .gitignore                    # Ignored files and folders
├── requirements.txt              # Python dependencies
└── GebetaDev Team - [MICHAEL].md          # This file
```

---

## Ignored files and folders (.gitignore)

- **Secrets:** `.env`, `.env.local`, `service-account*.json`, `admin_users.json`
- **Python:** `.venv/`, `__pycache__/`, `*.pyc`, `build/`, `dist/`, etc.
- **Runtime:** `uploads/`, `*.log`, `registrations.json`
- **Generated/setup:** `cursor_project_file_structure_setup.md`, `embed_logo.py`
- **Migrations output:** `migration/`
- **IDE/OS:** `.idea/`, `.vscode/`, `.DS_Store`

---

## How to run

1. **Copy env:** `cp .env.example .env` and set `DATABASE_URL`, `SUPABASE_URL`, etc.
2. **Install:** `pip install -r requirements.txt`
3. **DB:** Run migrations (e.g. `psql "$DATABASE_URL" -f migrations/000_complete_registrations_schema.sql`).
4. **Start API:** from project root:
   - `python run.py` (recommended), or
   - `python server.py`, or
   - `python -m api.app`

Default URL: **http://localhost:5050/** (registration), **http://localhost:5050/admin** (admin).

---

## Code structure (api/)

- **api/app.py**  
  - Flask app, CORS, paths (project root = parent of `api/`).  
  - **Helpers:** `generate_ref()`, `allowed_file()`, Supabase storage helpers, DB URL normalization, `get_db_connection()`, `_record_to_row()`, `insert_registration()`, `load_db_registrations()`, `get_registration_by_ref()`.  
  - **Routes:** `GET /`, `POST /register`, `GET /registrations`, `GET /stats`, `GET /file/...`, `GET /uploads/...`, and full admin set (`/admin`, `/admin/login`, `/admin/registrations`, `/admin/delete`, `/admin/update-status`, `/admin/download-zip`, `/admin/send-sms`, `/admin/file/...`).  
  - **Comments:** Docstrings and section comments for each task.

- **run.py**  
  - Loads `.env` from project root, imports `app` and `PORT` from `api.app`, runs `app.run()`.

- **server.py (root)**  
  - Thin launcher for backward compatibility; adds project root to `sys.path` and delegates to `api.app`.

---

## Database (PostgreSQL / Supabase)

- **Schema:** `bahiran_driver`.  
- **Table:** `bahiran_driver.registrations` (id, ref, firstname, lastname, fullname, phone, transport_type, brand, year, plate, platecode, plateletter, platenum, licence_file, idcard_file, libre_file, status, registered_at, created_at, updated_at).  
- **Migrations:** Use `000_complete_registrations_schema.sql` for a full fresh install; use `001`/`002` for incremental updates.

---

## Frontend

- **index.html:** Driver registration (transport type: Car / Motor / Bicycles), personal info, vehicle details, documents (Bicycles: ID only), terms checkbox.  
- **admin.html:** Admin panel (login, list, search, status, delete, download ZIP, SMS).  
- **Navigation:** Menu removed from registration page; admin page keeps Register | Admin nav.

---

## Comments and tasks

- All API functions and main tasks in `api/app.py` are documented with docstrings or section comments.  
- `run.py` has a module docstring and brief inline comments where useful.

---

_Last updated: GebetaDev Team - [MICHAEL] structure and production-ready layout._
