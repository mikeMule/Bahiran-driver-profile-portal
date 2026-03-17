#!/usr/bin/env python3
"""
Bahiran Delivery Driver Registration — Motor Driver Registration Backend (GebetaDev Team - [MICHAEL]).
Flask API: registration, admin, file serving.
Run from project root: python run.py  (or: python -m api.app)
API runs on http://localhost:5050
"""

from pathlib import Path
import os

# Project root (parent of api/). Load .env from project root.
_BASE = Path(__file__).resolve().parent.parent
_env_path = _BASE / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass

import json
import time
import uuid
import random
import string
import traceback
import datetime
import jwt
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ── Paths (project root = parent of api/) ─────────────────────────────────
BASE_DIR    = str(_BASE)
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
DATA_FILE   = os.path.join(BASE_DIR, "registrations.json")

MAX_FILE_MB = 5
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf"}
PORT        = int(os.environ.get("PORT", "5050"))

# Supabase — from .env (SERVICE_* from DevOps / Kong gateway)
SUPABASE_URL = (
    os.environ.get("SERVICE_URL_SUPABASEKONG")
    or os.environ.get("SERVICE_URL_SUPABASEKONG_8000")
    or os.environ.get("SUPABASE_URL")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    or os.environ.get("EXPO_PUBLIC_SUPABASE_URL")
)
SUPABASE_ANON_KEY = (
    os.environ.get("SERVICE_SUPABASEANON_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    or os.environ.get("EXPO_PUBLIC_SUPABASE_KEY")
)
# Service role key (optional; for admin operations if needed)
SUPABASE_SERVICE_KEY = os.environ.get("SERVICE_SUPABASESERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
# PostgreSQL connection (optional; for registrations, admin list, stats)
SUPABASE_DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
SUPABASE_DATABASE_POOLER_URL = os.environ.get("SUPABASE_DATABASE_POOLER_URL")

# Supabase Storage — bucket name for driver document uploads
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "driver-documents").strip()

# Optional override for the storage base URL (e.g. http://72.60.30.150:8000).
# Use this when SUPABASE_URL resolves to a hostname that is unreachable from the
# API server (e.g. an internal Docker/sslip.io URL). Falls back to SUPABASE_URL.
SUPABASE_STORAGE_BASE_URL = (
    os.environ.get("SUPABASE_STORAGE_URL")
    or os.environ.get("SUPABASE_STORAGE_BASE_URL")
    or SUPABASE_URL
)

# ── App setup ────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)  # we serve index manually
CORS(app)

# ── Helpers ──────────────────────────────────────────────────────────────
def generate_ref():
    """Generate a unique reference string (e.g. REF-ABC12345) for a new registration."""
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=5))
    return f"REF-{letters}{numbers}"

def allowed_file(filename):
    """Return True if filename has an allowed extension (.jpg, .jpeg, .png, .pdf)."""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXT


# ── Supabase Storage ─────────────────────────────────────────────────────

def upload_file_to_supabase(file_obj, storage_path):
    """Upload a file to Supabase Storage. Returns 'storage:PATH' or None.
    storage_path example: 'REF-ABC12345/licence.jpg'
    Files are stored under: driver-documents/REF-ABC12345/licence.jpg
    Uses service role key when available (bypasses RLS); falls back to anon key.
    """
    auth_key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    if not (SUPABASE_URL and auth_key):
        print(f"[Storage] Missing SUPABASE_URL or auth key — cannot upload {storage_path}")
        return None
    if not file_obj or not file_obj.filename:
        return None
    ext = os.path.splitext(file_obj.filename)[1].lower()
    mime = {
        ".pdf":  "application/pdf",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
    }.get(ext, "application/octet-stream")
    # Timeout: (connect_sec, read_sec). Longer read for slow links / large files.
    STORAGE_CONNECT_TIMEOUT = 15
    STORAGE_READ_TIMEOUT = 90
    try:
        import requests as req_lib
        file_bytes = file_obj.read()
        base = (SUPABASE_STORAGE_BASE_URL or SUPABASE_URL or "").rstrip("/")
        url = f"{base}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{storage_path}"
        headers = {
            "Authorization": f"Bearer {auth_key}",
            "Content-Type": mime,
            "x-upsert": "true",
        }
        print(f"[Storage] Uploading to {url} (key_type={'service' if SUPABASE_SERVICE_KEY else 'anon'})")
        resp = req_lib.post(
            url, headers=headers, data=file_bytes,
            timeout=(STORAGE_CONNECT_TIMEOUT, STORAGE_READ_TIMEOUT),
        )
        if resp.status_code in (200, 201):
            print(f"[Storage] Uploaded: {storage_path}")
            return f"storage:{storage_path}"
        else:
            print(f"[Storage] Upload failed ({resp.status_code}): {(resp.text or '')[:400]}")
            try:
                file_obj.seek(0)
            except Exception:
                pass
            return None
    except Exception as e:
        try:
            import requests as _req
            if isinstance(e, (_req.exceptions.Timeout, _req.exceptions.ConnectionError)):
                print(f"[Storage] Upload timed out or connection failed for {storage_path}: {e}")
            else:
                traceback.print_exc()
        except Exception:
            traceback.print_exc()
        try:
            file_obj.seek(0)
        except Exception:
            pass
        return None


def get_file_from_storage(storage_path):
    """Download file from Supabase Storage. Returns (bytes, content_type) or (None, None)."""
    auth_key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    if not (SUPABASE_URL and auth_key):
        return (None, None)
    try:
        import requests as req_lib
        base = (SUPABASE_STORAGE_BASE_URL or SUPABASE_URL or "").rstrip("/")
        url = f"{base}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{storage_path}"
        headers = {"Authorization": f"Bearer {auth_key}"}
        resp = req_lib.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            return (resp.content, content_type)
        return (None, None)
    except Exception:
        traceback.print_exc()
        return (None, None)


def _save_file_local(file_obj, folder, name):
    """Save file to UPLOAD_DIR/folder/name. Returns 'uploads/folder/name' or None. (Used only for admin/legacy.)"""
    try:
        dest_dir = os.path.join(UPLOAD_DIR, folder)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, name)
        file_obj.seek(0)
        file_obj.save(dest_path)
        return f"uploads/{folder}/{name}"
    except Exception as e:
        print(f"[Storage] Local save failed for {folder}/{name}: {e}")
        traceback.print_exc()
        return None


def save_file(file_obj, subfolder, ref_folder=None):
    """Save file to Supabase Storage only. No local uploads — everything goes to DB/Storage.
    ref_folder is the REF folder name used in storage path. Returns 'storage:PATH' or None on failure.
    """
    if not file_obj or not file_obj.filename or not allowed_file(file_obj.filename):
        return None
    ext  = os.path.splitext(file_obj.filename)[1].lower()
    name = f"{uuid.uuid4().hex}{ext}"
    folder = ref_folder if ref_folder else subfolder
    storage_path = f"{folder}/{name}"

    if not (SUPABASE_URL and SUPABASE_ANON_KEY):
        return None
    result = upload_file_to_supabase(file_obj, storage_path)
    return result


def load_db():
    """Load registrations from local JSON file (fallback when no DB configured)."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        traceback.print_exc()
        return []

def save_db(records):
    """Persist registrations to local JSON file."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception:
        traceback.print_exc()

def validate_phone(phone):
    """Return True if phone is a valid Ethiopian mobile (09/07, 10 digits)."""
    import re
    if not phone:
        return False
    phone = str(phone).strip().replace(" ", "").replace("-", "")
    # Accept: +25109..., +25107..., +2519..., +2517..., 09..., 07..., 9..., 7... (Ethiopian mobile)
    if re.match(r"^\+2510?[79]\d{8}$", phone):
        return True
    if re.match(r"^0[79]\d{8}$", phone):
        return True
    if re.match(r"^[79]\d{8}$", phone):
        return True
    return False


def _normalize_phone_for_duplicate(phone):
    """Return canonical 9-digit string (e.g. 912345678) for duplicate check, or None."""
    if not phone:
        return None
    s = str(phone).strip().replace(" ", "").replace("-", "")
    if not s:
        return None
    if s.startswith("+251"):
        s = s[4:].lstrip("0") or s[4:]
    elif s.startswith("251"):
        s = s[3:].lstrip("0") or s[3:]
    elif s.startswith("0") and len(s) >= 10:
        s = s[1:]
    if len(s) == 9 and s[0] in "79":
        return s
    return None


def check_duplicate_registration(phone, is_bike, plate=None):
    """Check if this phone (and plate for car/motor) is already registered.
    Returns (True, user_friendly_message) if duplicate, else (False, None).
    """
    existing = load_db_registrations() or []
    key_phone = _normalize_phone_for_duplicate(phone)
    if not key_phone:
        return (False, None)
    for r in existing:
        p = (r.get("phone") or "").strip()
        if not p:
            continue
        existing_key = _normalize_phone_for_duplicate(p)
        if existing_key != key_phone:
            continue
        # Same phone already registered
        if is_bike:
            return (True, "This phone number is already registered. Each person can register only once for Bicycles.")
        # Car/Motor: same phone = duplicate
        return (True, "This phone number is already registered. Each person can register only once.")
    if not is_bike and plate:
        # Car/Motor: also check plate (one registration per plate)
        plate_clean = (plate or "").strip().upper()
        if not plate_clean:
            return (False, None)
        for r in existing:
            if (r.get("transport_type") or "").lower() == "bike":
                continue
            p = (r.get("plate") or "").strip().upper()
            if p and p == plate_clean:
                return (True, "This plate number is already registered. Each vehicle can be registered only once.")
    return (False, None)


# ── Supabase API client (when URL + key are set) ───────────────────────────
_supabase_client = None

def get_supabase_client():
    """Return Supabase client when SUPABASE_URL and SUPABASE_ANON_KEY are set, else None."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    if not (SUPABASE_URL and SUPABASE_ANON_KEY):
        return None
    try:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL.strip(), SUPABASE_ANON_KEY.strip())
        return _supabase_client
    except Exception as e:
        traceback.print_exc()
        return None


# ── Database (Supabase / PostgreSQL) ──────────────────────────────────────
# Schema must match migrations/001_create_registrations.sql
DB_SCHEMA = "bahiran_driver"
DB_TABLE = "registrations"


def _normalize_db_url(url):
    """Use connection URL from .env. Encode password if it contains @ # $ so URI is valid."""
    if not url or not url.strip():
        return ""
    url = url.strip()
    # If URL already has encoded password (e.g. %40), use as-is after adding SSL
    if "%40" in url or "%23" in url:
        return url
    # Otherwise password may contain @ or # (e.g. from quoted .env). Encode password part.
    try:
        from urllib.parse import quote
        # Authority is between // and next / :  user:password@host:port
        if "//" not in url:
            return url
        pre, rest = url.split("//", 1)
        if "/" in rest:
            authority, path = rest.split("/", 1)
            path = "/" + path
        else:
            authority, path = rest, ""
        if "@" not in authority:
            return url
        # Last @ separates password from host (host may contain port)
        parts = authority.rsplit("@", 1)
        if len(parts) != 2:
            return url
        user_pass, host_port = parts[0], parts[1]
        if ":" not in user_pass:
            return url
        user, password = user_pass.split(":", 1)
        encoded_pass = quote(password, safe="")
        url = f"{pre}//{user}:{encoded_pass}@{host_port}{path}"
    except Exception:
        pass
    return url


def _strip_unsupported_query_params(url):
    """Remove query params psycopg2 doesn't accept (e.g. pgbouncer, options from Supabase)."""
    if "?" not in url:
        return url
    base, query = url.split("?", 1)
    from urllib.parse import parse_qs, urlencode
    params = parse_qs(query, keep_blank_values=False)
    # Keep only params psycopg2/libpq accept; drop pgbouncer, options, etc.
    allowed = {"sslmode", "sslcert", "sslkey", "sslrootcert", "sslcrl", "requirepeer"}
    kept = {k: v for k, v in params.items() if k.lower() in allowed}
    if not kept:
        return base
    return base + "?" + urlencode(kept, doseq=True)


def _get_db_url_with_ssl(url_raw):
    """Ensure connection URL has sslmode for Supabase (required). Strip unsupported params (e.g. pgbouncer)."""
    url = _normalize_db_url(url_raw or "")
    if not url:
        return url
    url = _strip_unsupported_query_params(url)
    if "sslmode=" in url:
        return url
    # Force SSL for Supabase (cloud or bahirandelivery); self-hosted IPs often use no SSL
    if ".supabase.co" in url or "bahirandelivery.cloud" in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def _direct_url_with_port(url, port):
    """Replace port in a postgres URL (e.g. 5432 -> 6543 for transaction pooler)."""
    import re
    return re.sub(r":5432/", f":{port}/", url, count=1)


def get_db_connection():
    """Return (connection, None) on success or (None, error_message) on failure."""
    import psycopg2
    urls_to_try = []
    if SUPABASE_DATABASE_URL:
        u = _get_db_url_with_ssl(SUPABASE_DATABASE_URL)
        if u:
            urls_to_try.append(u)
            # If Supabase host, also try port 6543 (transaction pooler) when 5432 is used
            if ":5432" in u and (".supabase.co" in u or "bahirandelivery.cloud" in u):
                u6543 = _direct_url_with_port(u, 6543)
                if u6543 not in urls_to_try:
                    urls_to_try.append(u6543)
    if SUPABASE_DATABASE_POOLER_URL:
        u = _get_db_url_with_ssl(SUPABASE_DATABASE_POOLER_URL)
        if u and u not in urls_to_try:
            urls_to_try.append(u)

    last_err_msg = ""
    for try_url in urls_to_try:
        try:
            conn = psycopg2.connect(try_url)
            return (conn, None)
        except psycopg2.OperationalError as e:
            last_err_msg = str(e).strip() or repr(e)
            err = last_err_msg.lower()
            if "tenant or user not found" in err:
                # Don't retry other regions — user must use exact URI from dashboard
                traceback.print_exc()
                return (None, last_err_msg + " Get the exact connection string from Supabase Dashboard → Connect → Session mode (copy URI).")
            if "could not translate host name" in err or "name or service not known" in err:
                traceback.print_exc()
                return (None, last_err_msg + " Use Session mode connection string from Supabase Dashboard → Connect (IPv4-friendly).")
            traceback.print_exc()
            return (None, last_err_msg)
        except Exception as e:
            traceback.print_exc()
            last_err_msg = str(e).strip() or repr(e)
            return (None, last_err_msg)
    return (None, last_err_msg or "No database URL configured.")


def _record_to_row(record):
    """Coerce record to row dict for DB/API (NOT NULL as str; vehicle fields may be None for bike)."""
    def s(v):
        return "" if v is None else str(v).strip()

    def vehicle_val(key):
        v = record.get(key)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return str(v).strip()

    return {
        "id": s(record.get("id")),
        "ref": s(record.get("ref")),
        "firstname": s(record.get("firstname")),
        "lastname": s(record.get("lastname")),
        "fullname": s(record.get("fullname")),
        "phone": s(record.get("phone")),
        "brand": vehicle_val("brand"),
        "year": vehicle_val("year"),
        "plate": vehicle_val("plate"),
        "platecode": vehicle_val("platecode"),
        "plateletter": vehicle_val("plateletter"),
        "platenum": vehicle_val("platenum"),
        "licence_file": record.get("licence_file"),
        "idcard_file": record.get("idcard_file"),
        "libre_file": record.get("libre_file"),
        "transport_type": s(record.get("transport_type")) or "motor",
        "status": s(record.get("status")) or "pending",
    }


def insert_registration(record):
    """Insert one registration into DB (direct Postgres preferred to avoid PostgREST; schema bahiran_driver).
    Returns (True, None) on success, (False, error_message) on failure.
    """
    # Prefer direct Postgres when configured (avoids PGRST002 on self-hosted Supabase)
    if SUPABASE_DATABASE_URL:
        try:
            conn, conn_err = get_db_connection()
        except Exception as _e:
            traceback.print_exc()
            conn, conn_err = None, str(_e)
        if conn is None:
            err = (conn_err or "Could not connect to database.").strip()
            if len(err) > 300:
                err = err[:297] + "..."
            return (False, err)
        try:
            params = _record_to_row(record)
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {DB_SCHEMA}.{DB_TABLE} (
                        id, ref, firstname, lastname, fullname, phone,
                        brand, year, plate, platecode, plateletter, platenum,
                        licence_file, idcard_file, libre_file, transport_type, status
                    ) VALUES (
                        %(id)s, %(ref)s, %(firstname)s, %(lastname)s, %(fullname)s, %(phone)s,
                        %(brand)s, %(year)s, %(plate)s, %(platecode)s, %(plateletter)s, %(platenum)s,
                        %(licence_file)s, %(idcard_file)s, %(libre_file)s, %(transport_type)s, %(status)s
                    )
                    """,
                    params,
                )
            conn.commit()
            return (True, None)
        except Exception as e:
            conn.rollback()
            err_msg = str(e).strip() or repr(e)
            traceback.print_exc()
            if len(err_msg) > 200:
                err_msg = err_msg[:197] + "..."
            return (False, err_msg)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    sb = get_supabase_client()
    if sb is not None:
        try:
            row = _record_to_row(record)
            sb.table(DB_TABLE).insert(row).execute()
            return (True, None)
        except Exception as e:
            err_msg = str(e).strip() or repr(e)
            traceback.print_exc()
            if len(err_msg) > 200:
                err_msg = err_msg[:197] + "..."
            return (False, err_msg)

    return (False, "Database not configured")


def _row_to_registration(row, columns):
    """Convert a DB row (tuple) to a dict like the JSON record."""
    out = dict(zip(columns, row))
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


def _api_row_to_registration(row):
    """Convert Supabase API row (dict) to same shape; serialize datetimes."""
    if not isinstance(row, dict):
        return row
    out = dict(row)
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


def load_db_registrations():
    """Return list of registrations from PostgreSQL (preferred) or Supabase API, or None if not configured/fails."""
    if SUPABASE_DATABASE_URL:
        try:
            conn, _ = get_db_connection()
        except Exception:
            traceback.print_exc()
            conn = None
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT id, ref, firstname, lastname, fullname, phone,
                               brand, year, plate, platecode, plateletter, platenum,
                               licence_file, idcard_file, libre_file, COALESCE(transport_type, 'motor') AS transport_type, status, registered_at
                        FROM {DB_SCHEMA}.{DB_TABLE}
                        ORDER BY registered_at DESC
                        """
                    )
                    cols = [d.name for d in cur.description]
                    rows = cur.fetchall()
                    return [_row_to_registration(r, cols) for r in rows]
            except Exception as e:
                traceback.print_exc()
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    sb = get_supabase_client()
    if sb is not None:
        try:
            r = sb.table(DB_TABLE).select(
                "id,ref,firstname,lastname,fullname,phone,brand,year,plate,platecode,plateletter,platenum,"
                "licence_file,idcard_file,libre_file,transport_type,status,registered_at"
            ).order("registered_at", desc=True).execute()
            rows = (r.data or []) if hasattr(r, "data") else []
            return [_api_row_to_registration(row) for row in rows]
        except Exception as e:
            traceback.print_exc()
            return None
    return None


def get_registration_by_ref(ref):
    """Return one registration dict by ref or id from PostgreSQL (preferred) or Supabase API, or None."""
    if SUPABASE_DATABASE_URL:
        try:
            conn, _ = get_db_connection()
        except Exception:
            traceback.print_exc()
            conn = None
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT id, ref, firstname, lastname, fullname, phone,
                               brand, year, plate, platecode, plateletter, platenum,
                               licence_file, idcard_file, libre_file, COALESCE(transport_type, 'motor') AS transport_type, status, registered_at
                        FROM {DB_SCHEMA}.{DB_TABLE}
                        WHERE ref = %s OR id = %s
                        LIMIT 1
                        """,
                        (ref, ref),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    cols = [d.name for d in cur.description]
                    return _row_to_registration(row, cols)
            except Exception as e:
                traceback.print_exc()
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    sb = get_supabase_client()
    if sb is not None:
        try:
            r = sb.table(DB_TABLE).select(
                "id,ref,firstname,lastname,fullname,phone,brand,year,plate,platecode,plateletter,platenum,"
                "licence_file,idcard_file,libre_file,transport_type,status,registered_at"
            ).or_(f"ref.eq.{ref},id.eq.{ref}").limit(1).execute()
            rows = (r.data or []) if hasattr(r, "data") else []
            if not rows:
                return None
            return _api_row_to_registration(rows[0])
        except Exception as e:
            traceback.print_exc()
            return None
    return None


# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    try:
        # ── Form fields ──
        firstname   = (request.form.get("firstname",   "") or "").strip()
        lastname    = (request.form.get("lastname",    "") or "").strip()
        phone       = (request.form.get("phone",       "") or "").strip()
        transport_type = (request.form.get("transport_type", "") or "").strip().lower()
        brand       = (request.form.get("brand",       "") or "").strip()
        year        = (request.form.get("year",        "") or "").strip()
        platecode   = (request.form.get("platecode",   "") or "").strip()
        plateletter = (request.form.get("plateletter", "") or "").strip()
        platenum    = (request.form.get("platenum",    "") or "").strip()

        # Bike = ID card only, no vehicle info. Decide this first so we never require vehicle fields for bike.
        is_bike = (transport_type == "bike") or not any([brand, year, platecode, plateletter, platenum])
        if is_bike:
            transport_type = "bike"
        elif transport_type not in ("car", "motor"):
            transport_type = "motor"

        # Auto-fill plate letters from region code if missing (only used for car/motor)
        REGION_LETTERS = {
            "1": "AA", "2": "OR", "3": "AM", "4": "SN", "5": "TG",
            "6": "SM", "7": "AF", "8": "BG", "9": "GB", "10": "HR"
        }
        if not plateletter and platecode:
            plateletter = REGION_LETTERS.get(platecode, "")

        # ── Validation ──
        errors = []

        if len(firstname) < 2:
            errors.append("First name is required (min 2 chars)")
        if len(lastname) < 2:
            errors.append("Last name is required (min 2 chars)")
        if not validate_phone(phone):
            errors.append("Invalid Ethiopian phone number")

        # Files — Bike: only ID card required; Car/Motor: licence, ID card, Libre
        licence_file = request.files.get("licence")
        idcard_file  = request.files.get("idcard")
        libre_file   = request.files.get("libre")
        def _has_file(f):
            return f and (getattr(f, "filename", None) or "").strip()

        # Vehicle fields required only for Car/Motor; Bike uses only ID + basic info
        if not is_bike:
            if not brand:
                errors.append("Vehicle brand is required")
            if not year or not year.isdigit() or not (2000 <= int(year) <= 2030):
                errors.append("Valid manufacture year (2000–2030) is required")
            if not platecode:
                errors.append("Region code is required")
            if not plateletter:
                errors.append("Plate letters are required")
            if not platenum:
                errors.append("Plate number is required")

        if not _has_file(idcard_file):
            errors.append("ID card file is required")
        elif not allowed_file(idcard_file.filename):
            errors.append("ID card: only JPG, JPEG, PNG, PDF allowed")
        elif idcard_file.content_length and idcard_file.content_length > MAX_FILE_MB * 1024 * 1024:
            errors.append("ID card file is too large (max {}MB)".format(MAX_FILE_MB))

        if not is_bike:
            for f, name in [(licence_file, "Driving licence"), (libre_file, "Libre")]:
                if not _has_file(f):
                    errors.append(f"{name} file is required")
                elif not allowed_file(f.filename):
                    errors.append(f"{name}: only JPG, JPEG, PNG, PDF allowed")
                elif f.content_length and f.content_length > MAX_FILE_MB * 1024 * 1024:
                    errors.append(f"{name} file is too large (max {MAX_FILE_MB}MB)")

        if errors:
            return jsonify({
                "success": False,
                "message": "; ".join(errors)
            }), 400

        # One registration per phone (bike) or per phone + plate (car/motor)
        plate_for_check = None if is_bike else f"{platecode}-{plateletter}-{platenum}"
        dup_found, dup_message = check_duplicate_registration(phone, is_bike, plate=plate_for_check)
        if dup_found:
            return jsonify({
                "success": False,
                "message": dup_message
            }), 400

        # ── Save ──
        ref    = generate_ref()
        reg_id = uuid.uuid4().hex[:12]
        subfolder = reg_id

        # Use REF as folder name in Supabase Storage: REF-XXXXX/uuid.ext
        _storage_ok = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
        if not _storage_ok:
            return jsonify({
                "success": False,
                "message": "File storage is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env and ensure the storage bucket exists."
            }), 500
        idcard_path = save_file(idcard_file, subfolder, ref_folder=ref)
        if is_bike:
            licence_path = None
            libre_path   = None
        else:
            licence_path = save_file(licence_file, subfolder, ref_folder=ref)
            libre_path   = save_file(libre_file, subfolder, ref_folder=ref)

        # All required files must have saved successfully
        if not idcard_path:
            return jsonify({
                "success": False,
                "message": "Failed to save ID card file. Check server logs for details (e.g. storage URL, auth, or bucket name)."
            }), 500
        if not is_bike and not all([licence_path, libre_path]):
            return jsonify({
                "success": False,
                "message": "Failed to save one or more uploaded files. Check server logs for storage errors."
            }), 500

        if is_bike:
            plate = None
            brand = year = platecode = plateletter = platenum = None
        else:
            plate = f"{platecode}-{plateletter}-{platenum}"

        record = {
            "id":             reg_id,
            "ref":            ref,
            "firstname":      firstname,
            "lastname":       lastname,
            "fullname":       f"{firstname} {lastname}",
            "phone":          phone,
            "transport_type": transport_type,
            "brand":          brand,
            "year":           year,
            "plate":          plate,
            "platecode":      platecode,
            "plateletter":    plateletter,
            "platenum":       platenum,
            "licence_file":   licence_path,
            "idcard_file":    idcard_path,
            "libre_file":     libre_path,
            "status":         "pending",
            "registered_at":  datetime.now().isoformat()
        }

        # Save to database only (no JSON file)
        if not (get_supabase_client() or SUPABASE_DATABASE_URL):
            return jsonify({
                "success": False,
                "message": "Database is not configured. Please contact support."
            }), 500
        ok, db_error = insert_registration(record)
        if not ok:
            err_text = (db_error if isinstance(db_error, str) else str(db_error or "")).strip()
            if not err_text:
                err_text = "Please try again or contact support."
            return jsonify({
                "success": False,
                "message": "Registration could not be saved to the database. " + err_text
            }), 500

        print(f"[NEW] {ref} - {record['fullname']} - {record.get('plate') or '—'} - {phone}")

        return jsonify({
            "success": True,
            "ref": ref,
            "id": reg_id,
            "message": "Registration submitted successfully"
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "Internal server error. Please try again later."
        }), 500


@app.route("/registrations", methods=["GET"])
def get_all():
    db = load_db_registrations()
    if db is None:
        db = []
    return jsonify({
        "success": True,
        "count": len(db),
        "data": db
    })


@app.route("/registration/<ref>", methods=["GET"])
def get_one(ref):
    record = get_registration_by_ref(ref)
    if record is None:
        return jsonify({
            "success": False,
            "message": "Registration not found"
        }), 404
    return jsonify({"success": True, "data": record})


@app.route("/stats", methods=["GET"])
def stats():
    db = load_db_registrations()
    if db is None:
        db = []
    return jsonify({
        "success": True,
        "total": len(db),
        "pending": sum(1 for r in db if r.get("status") == "pending"),
        "approved": sum(1 for r in db if r.get("status") == "approved"),
    })


# Serve CSS from css/ folder
@app.route("/css/<path:filename>")
def serve_css(filename):
    css_dir = os.path.join(BASE_DIR, "css")
    response = send_from_directory(css_dir, filename)
    response.headers['Content-Type'] = 'text/css'
    return response


# Serve static assets (logo, favicon, etc.)
@app.route("/assets/<path:filename>")
def serve_assets(filename):
    assets_dir = os.path.join(BASE_DIR, "assets")
    response = send_from_directory(assets_dir, filename)
    if filename.endswith('.png'):
        response.headers['Content-Type'] = 'image/png'
    return response


# Serve the frontend (index.html) with CSS and logo inlined to avoid 404s
@app.route("/", methods=["GET"])
@app.route("/index.html", methods=["GET"])
def serve_frontend():
    import base64
    html_path = os.path.join(BASE_DIR, "index.html")
    css_path = os.path.join(BASE_DIR, "css", "register.css")
    logo_path = os.path.join(BASE_DIR, "assets", "logo.png")
    if not os.path.exists(html_path):
        return "<h2>index.html not found</h2>", 404
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    # Inline CSS so it always loads (no /css/ request)
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        html = html.replace('<link rel="stylesheet" href="/css/register.css">', '<style>\n' + css + '\n</style>')
    # Inline logo as data URI so favicon and header logo load (no /assets/ request)
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("ascii")
        data_uri = "data:image/png;base64," + logo_b64
        html = html.replace('href="/assets/logo.png"', 'href="' + data_uri + '"')
        html = html.replace('src="/assets/logo.png"', 'src="' + data_uri + '"')
    else:
        html = html.replace('<link rel="icon" href="/assets/logo.png" type="image/png">', '')
        html = html.replace('<div class="logo-box"><img src="/assets/logo.png" alt="Bahiran Delivery Driver Registration" class="logo-img"></div>',
                            '<div class="logo-box">&#127949;</div>')
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# Serve files from Supabase Storage
@app.route("/file/<path:storage_path>")
def serve_storage_file(storage_path):
    """Stream a file from Supabase Storage (stored as 'storage:PATH' in DB)."""
    data, content_type = get_file_from_storage(storage_path)
    if data is None:
        return "File not found", 404
    from flask import Response
    return Response(data, mimetype=content_type)

@app.route("/uploads/<path:filename>")
def serve_uploaded_file(filename):
    """Legacy: local uploads removed — files are in Supabase Storage only."""
    if filename.startswith("storage/"):
        path = filename[8:].strip()
        data, content_type = get_file_from_storage(path)
        if data is None:
            return "File not found", 404
        from flask import Response
        return Response(data, mimetype=content_type)
    if not os.path.isdir(UPLOAD_DIR):
        return "File not found", 404
    return send_from_directory(UPLOAD_DIR, filename)


# ═══════════════════════════════════════════════════════════════
#  ADMIN PANEL ROUTES
# ═══════════════════════════════════════════════════════════════

import hashlib
import functools
from flask import session, redirect, url_for

app.secret_key = os.environ.get("ADMIN_SECRET_KEY", "motoreg-admin-secret-2024")
# Admin session: 15 min inactivity = logout; 30 min absolute = logout on next request
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # so cookie is sent on page refresh
app.config["SESSION_COOKIE_HTTPONLY"] = True
ADMIN_SESSION_INACTIVITY_MIN = 15
ADMIN_SESSION_ABSOLUTE_MIN = 30

# Admin credentials — stored in admin_users.json (pin-based, no DB)
ADMIN_USERS_FILE = os.path.join(BASE_DIR, "admin_users.json")

def _load_admin_users():
    if os.path.exists(ADMIN_USERS_FILE):
        try:
            with open(ADMIN_USERS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    # Default admin: username=admin, pin=4067
    default = [{"username": "admin", "pin_hash": hashlib.sha256("4067".encode()).hexdigest()}]
    with open(ADMIN_USERS_FILE, "w") as f:
        json.dump(default, f, indent=2)
    return default

def _check_admin(username, pin):
    users = _load_admin_users()
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    return any(u["username"] == username and u["pin_hash"] == pin_hash for u in users)

def _admin_session_valid():
    """Check session: 15 min inactivity or 30 min absolute → invalid. Missing timestamps = treat as valid and set them."""
    if not session.get("admin_logged_in"):
        return False
    now = time.time()
    last = session.get("last_activity") or 0
    login_at = session.get("login_at") or 0
    # If timestamps missing (e.g. old session or just after login), accept and set them so refresh doesn't log out
    if last == 0 or login_at == 0:
        session["last_activity"] = now
        session["login_at"] = session.get("login_at") or now
        session.modified = True
        return True
    if now - last > ADMIN_SESSION_INACTIVITY_MIN * 60:
        return False
    if now - login_at > ADMIN_SESSION_ABSOLUTE_MIN * 60:
        return False
    return True


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _admin_session_valid():
            session.clear()
            return jsonify({"success": False, "message": "Session expired. Please log in again."}), 401
        session["last_activity"] = time.time()
        session.modified = True
        return f(*args, **kwargs)
    return decorated


def _admin_html_path():
    """Resolve admin.html: prefer admin/admin.html, then admin.html in project root."""
    base = Path(BASE_DIR).resolve()
    for candidate in (base / "admin" / "admin.html", base / "admin.html"):
        if candidate.is_file():
            return str(candidate)
    return None


@app.route("/admin", methods=["GET"])
@app.route("/admin.html", methods=["GET"])
def serve_admin():
    admin_path = _admin_html_path()
    if not admin_path:
        return "<h2>admin.html not found</h2><p>Looked in: %s and %s</p>" % (
            os.path.join(BASE_DIR, "admin", "admin.html"),
            os.path.join(BASE_DIR, "admin.html"),
        ), 404
    with open(admin_path, "r", encoding="utf-8") as f:
        html = f.read()
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    pin      = (data.get("pin") or "").strip()
    if _check_admin(username, pin):
        session.permanent = True
        session["admin_logged_in"] = True
        session["admin_user"] = username
        session["login_at"] = time.time()
        session["last_activity"] = time.time()
        session.modified = True
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Invalid username or PIN"}), 401


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/admin/registrations", methods=["GET"])
@admin_required
def admin_get_registrations():
    db = load_db_registrations()
    if db is None:
        db = []
    # Build document URLs through /admin/file/ (authenticated; works for Storage and local uploads)
    for r in db:
        for field in ("licence_file", "idcard_file", "libre_file"):
            val = (r.get(field) or "").strip() if r.get(field) is not None else ""
            if val and val.startswith("storage:"):
                path = val[8:]
                r[f"{field}_url"] = f"/admin/file/{path}"
            elif val:
                # Local path e.g. uploads/reg_id/file.png — route via admin so auth applies
                r[f"{field}_url"] = f"/admin/file/{val}"
            else:
                r[f"{field}_url"] = ""
    return jsonify({"success": True, "count": len(db), "data": db})


@app.route("/admin/delete", methods=["POST"])
@admin_required
def admin_delete_single():
    """Delete one registration by ref (or id)."""
    data = request.get_json() or {}
    ref = (data.get("ref") or "").strip()
    if not ref:
        return jsonify({"success": False, "message": "ref required"}), 400
    if SUPABASE_DATABASE_URL:
        conn, conn_err = get_db_connection()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {DB_SCHEMA}.{DB_TABLE} WHERE ref = %s OR id = %s",
                        (ref, ref),
                    )
                    deleted = cur.rowcount
                conn.commit()
                if deleted:
                    return jsonify({"success": True})
                return jsonify({"success": False, "message": "Record not found"}), 404
            except Exception as e:
                conn.rollback()
                traceback.print_exc()
                return jsonify({"success": False, "message": str(e)}), 500
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    sb = get_supabase_client()
    if sb:
        try:
            sb.table(DB_TABLE).delete().eq("ref", ref).execute()
            return jsonify({"success": True})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"success": False, "message": "Database not configured"}), 500


@app.route("/admin/delete-bulk", methods=["POST"])
@admin_required
def admin_delete_bulk():
    """Delete multiple registrations by refs (list)."""
    data = request.get_json() or {}
    refs = data.get("refs", [])
    if not refs or not isinstance(refs, list):
        return jsonify({"success": False, "message": "refs array required"}), 400
    refs = [str(r).strip() for r in refs if str(r).strip()]
    if not refs:
        return jsonify({"success": False, "message": "No refs provided"}), 400
    if SUPABASE_DATABASE_URL:
        conn, conn_err = get_db_connection()
        if conn is not None:
            try:
                deleted = 0
                with conn.cursor() as cur:
                    for ref in refs:
                        cur.execute(
                            f"DELETE FROM {DB_SCHEMA}.{DB_TABLE} WHERE ref = %s OR id = %s",
                            (ref, ref),
                        )
                        deleted += cur.rowcount
                conn.commit()
                return jsonify({"success": True, "deleted": deleted})
            except Exception as e:
                conn.rollback()
                traceback.print_exc()
                return jsonify({"success": False, "message": str(e)}), 500
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    sb = get_supabase_client()
    if sb:
        try:
            for ref in refs:
                sb.table(DB_TABLE).delete().eq("ref", ref).execute()
            return jsonify({"success": True, "deleted": len(refs)})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"success": False, "message": "Database not configured"}), 500


@app.route("/admin/update-status", methods=["POST"])
@admin_required
def admin_update_status():
    data   = request.get_json() or {}
    ref    = (data.get("ref") or "").strip()
    status = (data.get("status") or "").strip()
    if not ref or status not in ("approved", "rejected", "pending"):
        return jsonify({"success": False, "message": "Invalid ref or status"}), 400
    if SUPABASE_DATABASE_URL:
        conn, conn_err = get_db_connection()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {DB_SCHEMA}.{DB_TABLE} SET status = %s WHERE ref = %s OR id = %s",
                        (status, ref, ref),
                    )
                    updated = cur.rowcount
                conn.commit()
                if updated:
                    return jsonify({"success": True})
                return jsonify({"success": False, "message": "Record not found"}), 404
            except Exception as e:
                conn.rollback()
                traceback.print_exc()
                return jsonify({"success": False, "message": str(e)}), 500
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    sb = get_supabase_client()
    if sb:
        try:
            sb.table(DB_TABLE).update({"status": status}).or_(f"ref.eq.{ref},id.eq.{ref}").execute()
            return jsonify({"success": True})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"success": False, "message": "Database not configured"}), 500


@app.route("/admin/download-zip", methods=["POST"])
@admin_required
def admin_download_zip():
    """Build a ZIP of driver info (JSON summary) for selected refs."""
    import zipfile, io
    data = request.get_json() or {}
    refs = data.get("refs", [])
    if not refs:
        return jsonify({"success": False, "message": "No refs provided"}), 400

    db = load_db_registrations()
    if not db:
        db = []
    records = [r for r in db if r.get("ref") in refs]
    if not records:
        return jsonify({"success": False, "message": "No records found"}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in records:
            firstname = r.get("firstname", "driver").replace(" ", "_")
            phone     = r.get("phone", "0000000000")
            # Normalize phone to start with 09
            if phone.startswith("+2519") or phone.startswith("+2517"):
                phone = "0" + phone[4:]
            elif phone.startswith("+251"):
                phone = "0" + phone[4:]
            elif not phone.startswith("0"):
                phone = "0" + phone
            folder = f"{firstname}-{phone}"
            # Write driver info as JSON
            info = {k: v for k, v in r.items() if not k.endswith("_url")}
            zf.writestr(f"{folder}/info.json", json.dumps(info, indent=2, ensure_ascii=False))
            # Download and include files from Supabase Storage
            bucket_prefix = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}" if SUPABASE_URL else ""
            for field, label in [("licence_file", "licence"), ("idcard_file", "idcard"), ("libre_file", "libre")]:
                val = r.get(field, "")
                if val and val.startswith("storage:"):
                    path = val[8:]
                    ext  = os.path.splitext(path)[1] or ".jpg"
                    file_data, _ = get_file_from_storage(path)
                    if file_data:
                        zf.writestr(f"{folder}/{label}{ext}", file_data)
    buf.seek(0)
    from flask import send_file
    zip_name = f"drivers-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return send_file(buf, mimetype="application/zip",
                     as_attachment=True, download_name=zip_name)


@app.route("/admin/send-sms", methods=["POST"])
@admin_required
def admin_send_sms():
    """Placeholder SMS route — wire up your SMS provider here."""
    data    = request.get_json() or {}
    phones  = data.get("phones", [])
    message = (data.get("message") or "").strip()
    if not phones or not message:
        return jsonify({"success": False, "message": "phones and message required"}), 400
    # TODO: integrate Ethio Telecom / Africa's Talking / etc.
    print(f"[SMS] Would send to {len(phones)} numbers: {message[:80]}")
    return jsonify({
        "success": True,
        "message": f"SMS queued for {len(phones)} recipient(s). (Provider not yet wired up)"
    })
@app.route("/admin/file/<path:storage_path>")
@admin_required
def admin_serve_file(storage_path):
    """Serve file from Supabase Storage or local uploads/ (authenticated). Used by admin panel."""
    # Local uploads: path is "uploads/reg_id/filename.ext"
    if storage_path.startswith("uploads/"):
        rel = storage_path[8:].lstrip("/")
        if not rel or ".." in rel:
            return "File not found", 404
        try:
            return send_from_directory(
                UPLOAD_DIR, rel,
                mimetype=None,
                as_attachment=False,
            )
        except Exception:
            return "File not found", 404
    # Supabase Storage: path is "REF-XXXXX/uuid.ext"
    data, content_type = get_file_from_storage(storage_path)
    if data is None:
        return "File not found", 404
    from flask import Response
    return Response(data, mimetype=content_type,
                    headers={"Cache-Control": "private, max-age=3600"})


# ── Start ────────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def api_health():
    """Return storage and DB config status (no secrets). Use to verify env vars in deployment."""
    return jsonify({
        "ok": True,
        "storage": {
            "configured": bool(SUPABASE_URL and SUPABASE_ANON_KEY),
            "bucket": SUPABASE_STORAGE_BUCKET,
            "url_set": bool(SUPABASE_URL),
            "key_set": bool(SUPABASE_ANON_KEY),
        },
        "database_configured": bool(SUPABASE_DATABASE_URL or SUPABASE_DATABASE_POOLER_URL),
    })

# ── API Routes for Restaurant Registration ──────────────────────────────

@app.route("/api/v1/users/signup", methods=["POST"])
def api_users_signup():
    """Send OTP for phone signup."""
    try:
        data = request.get_json()
        phone = data.get("phone", "").strip()

        if not phone.startswith("+") or len(phone) < 10:
            return jsonify({"message": "Invalid phone number format"}), 400

        # Here you would integrate with your SMS service to send OTP
        # For now, we'll just return success
        return jsonify({
            "message": "OTP sent successfully",
            "phone": phone
        }), 200

    except Exception as e:
        return jsonify({"message": str(e)}), 500


@app.route("/api/v1/users/verifySignupOTP", methods=["POST"])
def api_users_verify_otp():
    """Verify OTP and return token."""
    try:
        data = request.get_json()
        phone = data.get("phone", "").strip()
        code = data.get("code", "").strip()
        password = data.get("password", "").strip()
        password_confirm = data.get("passwordConfirm", "").strip()

        if not phone or not code or len(code) != 6:
            return jsonify({"message": "Invalid phone or OTP code"}), 400

        if password != password_confirm:
            return jsonify({"message": "Passwords do not match"}), 400

        # Here you would verify the OTP with your SMS service
        # For now, we'll accept any 6-digit code and return a mock token
        if not code.isdigit() or len(code) != 6:
            return jsonify({"message": "Invalid OTP code"}), 400

        # Generate a mock JWT token
        import jwt
        import datetime
        token_payload = {
            "phone": phone,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }
        token = jwt.encode(token_payload, "your-secret-key", algorithm="HS256")

        return jsonify({
            "message": "OTP verified successfully",
            "token": token
        }), 200

    except Exception as e:
        return jsonify({"message": str(e)}), 500


@app.route("/api/v1/restaurant-applications/register", methods=["POST"])
def api_restaurant_register():
    """Register restaurant with token authentication."""
    try:
        # Check for authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"message": "Authorization token required"}), 401

        token = auth_header.split(" ")[1]

        # Here you would verify the JWT token
        # For now, we'll accept any token
        try:
            import jwt
            decoded = jwt.decode(token, "your-secret-key", algorithms=["HS256"])
            phone = decoded.get("phone")
        except:
            return jsonify({"message": "Invalid token"}), 401

        # Get form data
        first_name = request.form.get("firstName", "").strip()
        last_name = request.form.get("lastName", "").strip()
        restaurant_name = request.form.get("restaurantName", "").strip()
        restaurant_address = request.form.get("restaurantAddress", "").strip()
        fcn = request.form.get("fcn", "").strip()
        tin_number = request.form.get("tinNumber", "").strip()
        menu_type = request.form.get("menuType", "text")

        # Validate required fields
        if not all([first_name, last_name, restaurant_name, restaurant_address, fcn, tin_number]):
            return jsonify({"message": "All fields are required"}), 400

        # Handle menu data
        menu_data = None
        if menu_type == "text":
            menu_data = request.form.get("menuText", "").strip()
        elif menu_type == "image":
            menu_file = request.files.get("menuImage")
            if menu_file:
                # Here you would save the file and store the path
                menu_data = f"image:{menu_file.filename}"
        elif menu_type == "file":
            menu_file = request.files.get("menuFile")
            if menu_file:
                # Here you would save the file and store the path
                menu_data = f"file:{menu_file.filename}"

        # Handle license file
        license_file = request.files.get("license")
        license_path = None
        if license_file:
            # Here you would save the file and store the path
            license_path = f"license:{license_file.filename}"

        # Here you would save to database
        # For now, we'll just return success
        registration_data = {
            "firstName": first_name,
            "lastName": last_name,
            "phone": phone,
            "restaurantName": restaurant_name,
            "restaurantAddress": restaurant_address,
            "fcn": fcn,
            "tinNumber": tin_number,
            "menuType": menu_type,
            "menuData": menu_data,
            "license": license_path,
            "status": "pending",
            "registeredAt": datetime.datetime.utcnow().isoformat()
        }

        return jsonify({
            "message": "Restaurant registration successful",
            "data": registration_data
        }), 201

    except Exception as e:
        return jsonify({"message": str(e)}), 500


if __name__ == "__main__":
    print("=" * 60)
    print("  Bahiran Delivery Driver Registration - Registration Server")
    print("=" * 60)
    print(f"  Frontend   : http://localhost:{PORT}/")
    print(f"  API submit : http://localhost:{PORT}/register")
    print(f"  All records: http://localhost:{PORT}/registrations")
    print(f"  Stats      : http://localhost:{PORT}/stats")
    if get_supabase_client():
        print(f"  Storage   : Supabase (API)")
    elif SUPABASE_DATABASE_URL:
        print(f"  Storage   : Supabase (PostgreSQL)")
    else:
        print(f"  Storage   : JSON file")
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        print(f"  Files      : Supabase Storage only (bucket: {SUPABASE_STORAGE_BUCKET})")
    else:
        print(f"  Files      : not configured (SUPABASE_URL + key required for uploads)")
    print("=" * 60)

    # Check DB connection when SUPABASE_DATABASE_URL is set
    if SUPABASE_DATABASE_URL or SUPABASE_DATABASE_POOLER_URL:
        conn, err = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                conn.close()
                print("  DB         : OK (PostgreSQL connected)")
            except Exception as e:
                print(f"  DB         : WARN (connected but query failed: {e})")
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
        else:
            print(f"  DB         : FAIL - {err}")
        print("=" * 60)
    else:
        print("  DB         : not configured (SUPABASE_DATABASE_URL not set)")
        print("=" * 60)

    print("  Press Ctrl+C to stop\n")

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)