#!/usr/bin/env python3
"""
MotoReg Ethiopia — Motor Driver Registration Backend
Run: python server.py
API runs on http://localhost:5050
"""

from pathlib import Path
import os

# Load .env from project root (before other imports that may use env vars)
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass

import json
import uuid
import random
import string
import traceback
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ── Paths ────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
DATA_FILE   = os.path.join(BASE_DIR, "registrations.json")

MAX_FILE_MB = 5
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf"}
PORT        = int(os.environ.get("PORT", "5050"))

# Supabase (from .env) — URL + key only (no Postgres connection string)
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("EXPO_PUBLIC_SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("EXPO_PUBLIC_SUPABASE_KEY")
# Optional: direct Postgres URL (if set, used as fallback; Supabase API preferred when URL+key set)
SUPABASE_DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL")
SUPABASE_DATABASE_POOLER_URL = os.environ.get("SUPABASE_DATABASE_POOLER_URL")

# Supabase Storage — bucket name for driver document uploads
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "driver-documents").strip()

# Google Drive (disabled — requires Google Workspace Shared Drive; using Supabase Storage instead)
GOOGLE_DRIVE_CREDENTIALS = None
GOOGLE_DRIVE_FOLDER_ID = ""

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── App setup ────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)  # we serve index manually
CORS(app)

# ── Helpers ──────────────────────────────────────────────────────────────
def generate_ref():
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=5))
    return f"REF-{letters}{numbers}"

def allowed_file(filename):
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXT


# ── Supabase Storage ─────────────────────────────────────────────────────

def upload_file_to_supabase(file_obj, storage_path):
    """Upload a file to Supabase Storage. Returns 'storage:PATH' or None.
    storage_path example: 'REF-ABC12345/licence.jpg'
    Files are stored under: driver-documents/REF-ABC12345/licence.jpg
    """
    if not (SUPABASE_URL and SUPABASE_ANON_KEY):
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
    try:
        import requests as req_lib
        file_bytes = file_obj.read()
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{storage_path}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": mime,
            "x-upsert": "true",
        }
        resp = req_lib.post(url, headers=headers, data=file_bytes, timeout=30)
        if resp.status_code in (200, 201):
            print(f"[Storage] Uploaded: {storage_path}")
            return f"storage:{storage_path}"
        else:
            print(f"[Storage] Upload failed ({resp.status_code}): {resp.text[:200]}")
            file_obj.seek(0)
            return None
    except Exception:
        traceback.print_exc()
        try:
            file_obj.seek(0)
        except Exception:
            pass
        return None


def get_file_from_storage(storage_path):
    """Download file from Supabase Storage. Returns (bytes, content_type) or (None, None)."""
    if not (SUPABASE_URL and SUPABASE_ANON_KEY):
        return (None, None)
    try:
        import requests as req_lib
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{storage_path}"
        headers = {"Authorization": f"Bearer {SUPABASE_ANON_KEY}"}
        resp = req_lib.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            return (resp.content, content_type)
        return (None, None)
    except Exception:
        traceback.print_exc()
        return (None, None)


def save_file(file_obj, subfolder, drive_parent_id=None):
    """Save file to Supabase Storage (preferred) or local uploads/ (fallback).
    drive_parent_id is kept for API compatibility but repurposed as the REF folder name.
    Storage path: REF-XXXXX/uuid.ext  inside the driver-documents bucket.
    Returns 'storage:PATH' or local relative path.
    """
    if not file_obj or not file_obj.filename or not allowed_file(file_obj.filename):
        return None
    ext  = os.path.splitext(file_obj.filename)[1].lower()
    name = f"{uuid.uuid4().hex}{ext}"

    # Use drive_parent_id as the REF-based folder name when available
    folder = drive_parent_id if drive_parent_id else subfolder
    storage_path = f"{folder}/{name}"

    # Try Supabase Storage first
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        result = upload_file_to_supabase(file_obj, storage_path)
        if result:
            return result
        # rewind already done inside upload_file_to_supabase on failure

    # Fallback: local disk
    dest_dir = os.path.join(UPLOAD_DIR, subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, name)
    file_obj.save(path)
    print(f"[Local] Saved: {path}")
    return os.path.join("uploads", subfolder, name).replace("\\", "/")


def get_file_from_drive(file_id):
    """Legacy shim — kept so /file/<id> route still works for old Drive-stored files."""
    return (None, None)

def load_db():
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
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception:
        traceback.print_exc()

def validate_phone(phone):
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
    sep = "&" if "?" in url else "?"
    return url + sep + "sslmode=require"


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
            # If direct host (db.xxx.supabase.co), also try port 6543 (transaction pooler)
            if "db." in u and ".supabase.co" in u and ":5432" in u:
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
    """Coerce record to row dict for DB/API (NOT NULL as str, nullable as-is)."""
    def s(v):
        return "" if v is None else str(v).strip()
    return {
        "id": s(record.get("id")),
        "ref": s(record.get("ref")),
        "firstname": s(record.get("firstname")),
        "lastname": s(record.get("lastname")),
        "fullname": s(record.get("fullname")),
        "phone": s(record.get("phone")),
        "brand": s(record.get("brand")),
        "year": s(record.get("year")),
        "plate": s(record.get("plate")),
        "platecode": s(record.get("platecode")),
        "plateletter": s(record.get("plateletter")),
        "platenum": s(record.get("platenum")),
        "licence_file": record.get("licence_file"),
        "idcard_file": record.get("idcard_file"),
        "libre_file": record.get("libre_file"),
        "status": s(record.get("status")) or "pending",
    }


def insert_registration(record):
    """Insert one registration into public.registrations (Supabase API or Postgres).
    Returns (True, None) on success, (False, error_message) on failure.
    """
    sb = get_supabase_client()
    if sb is not None:
        try:
            row = _record_to_row(record)
            sb.table("registrations").insert(row).execute()
            return (True, None)
        except Exception as e:
            err_msg = str(e).strip() or repr(e)
            traceback.print_exc()
            if len(err_msg) > 200:
                err_msg = err_msg[:197] + "..."
            return (False, err_msg)

    if not SUPABASE_DATABASE_URL:
        return (False, "Database not configured")
    conn, conn_err = get_db_connection()
    if conn is None:
        err = (conn_err or "Could not connect to database.").strip()
        if len(err) > 300:
            err = err[:297] + "..."
        return (False, err)
    try:
        params = _record_to_row(record)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.registrations (
                    id, ref, firstname, lastname, fullname, phone,
                    brand, year, plate, platecode, plateletter, platenum,
                    licence_file, idcard_file, libre_file, status
                ) VALUES (
                    %(id)s, %(ref)s, %(firstname)s, %(lastname)s, %(fullname)s, %(phone)s,
                    %(brand)s, %(year)s, %(plate)s, %(platecode)s, %(plateletter)s, %(platenum)s,
                    %(licence_file)s, %(idcard_file)s, %(libre_file)s, %(status)s
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
    """Return list of registrations from Supabase API or PostgreSQL, or None if not configured/fails."""
    sb = get_supabase_client()
    if sb is not None:
        try:
            r = sb.table("registrations").select(
                "id,ref,firstname,lastname,fullname,phone,brand,year,plate,platecode,plateletter,platenum,"
                "licence_file,idcard_file,libre_file,status,registered_at"
            ).order("registered_at", desc=True).execute()
            rows = (r.data or []) if hasattr(r, "data") else []
            return [_api_row_to_registration(row) for row in rows]
        except Exception as e:
            traceback.print_exc()
            return None
    if not SUPABASE_DATABASE_URL:
        return None
    conn, _ = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ref, firstname, lastname, fullname, phone,
                       brand, year, plate, platecode, plateletter, platenum,
                       licence_file, idcard_file, libre_file, status, registered_at
                FROM public.registrations
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
        conn.close()


def get_registration_by_ref(ref):
    """Return one registration dict by ref or id from Supabase API or PostgreSQL, or None."""
    sb = get_supabase_client()
    if sb is not None:
        try:
            r = sb.table("registrations").select(
                "id,ref,firstname,lastname,fullname,phone,brand,year,plate,platecode,plateletter,platenum,"
                "licence_file,idcard_file,libre_file,status,registered_at"
            ).or_(f"ref.eq.{ref},id.eq.{ref}").limit(1).execute()
            rows = (r.data or []) if hasattr(r, "data") else []
            if not rows:
                return None
            return _api_row_to_registration(rows[0])
        except Exception as e:
            traceback.print_exc()
            return None
    if not SUPABASE_DATABASE_URL:
        return None
    conn, _ = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ref, firstname, lastname, fullname, phone,
                       brand, year, plate, platecode, plateletter, platenum,
                       licence_file, idcard_file, libre_file, status, registered_at
                FROM public.registrations
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
        conn.close()


# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    try:
        # ── Form fields ──
        firstname   = (request.form.get("firstname",   "") or "").strip()
        lastname    = (request.form.get("lastname",    "") or "").strip()
        phone       = (request.form.get("phone",       "") or "").strip()
        brand       = (request.form.get("brand",       "") or "").strip()
        year        = (request.form.get("year",        "") or "").strip()
        platecode   = (request.form.get("platecode",   "") or "").strip()
        plateletter = (request.form.get("plateletter", "") or "").strip()
        platenum    = (request.form.get("platenum",    "") or "").strip()

        # Auto-fill plate letters from region code if missing
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
        if not brand:
            errors.append("Motor brand is required")
        if not year or not year.isdigit() or not (2000 <= int(year) <= 2030):
            errors.append("Valid manufacture year (2000–2030) is required")
        if not platecode:
            errors.append("Region code is required")
        if not plateletter:
            errors.append("Plate letters are required")
        if not platenum:
            errors.append("Plate number is required")

        # Files
        licence_file = request.files.get("licence")
        idcard_file  = request.files.get("idcard")
        libre_file   = request.files.get("libre")

        for f, name in [(licence_file, "Driving licence"), (idcard_file, "ID card"), (libre_file, "Libre")]:
            if not f or not f.filename:
                errors.append(f"{name} file is required")
            elif not allowed_file(f.filename):
                errors.append(f"{name}: only JPG, JPEG, PNG, PDF allowed")
            elif f.content_length > MAX_FILE_MB * 1024 * 1024:
                errors.append(f"{name} file is too large (max {MAX_FILE_MB}MB)")

        if errors:
            return jsonify({
                "success": False,
                "message": "; ".join(errors)
            }), 400

        # ── Save ──
        ref    = generate_ref()
        reg_id = uuid.uuid4().hex[:12]
        subfolder = reg_id

        # Use REF as folder name in Supabase Storage: REF-XXXXX/uuid.ext
        licence_path = save_file(licence_file, subfolder, drive_parent_id=ref)
        idcard_path  = save_file(idcard_file,  subfolder, drive_parent_id=ref)
        libre_path   = save_file(libre_file,   subfolder, drive_parent_id=ref)

        # All files must have saved successfully
        if not all([licence_path, idcard_path, libre_path]):
            return jsonify({
                "success": False,
                "message": "Failed to save one or more uploaded files"
            }), 500

        plate = f"{platecode}-{plateletter}-{platenum}"

        record = {
            "id":           reg_id,
            "ref":          ref,
            "firstname":    firstname,
            "lastname":     lastname,
            "fullname":     f"{firstname} {lastname}",
            "phone":        phone,
            "brand":        brand,
            "year":         year,
            "plate":        plate,
            "platecode":    platecode,
            "plateletter":  plateletter,
            "platenum":     platenum,
            "licence_file": licence_path,
            "idcard_file":  idcard_path,
            "libre_file":   libre_path,
            "status":       "pending",
            "registered_at": datetime.now().isoformat()
        }

        # Database insert when Supabase API or Postgres URL is configured
        if get_supabase_client() or SUPABASE_DATABASE_URL:
            ok, db_error = insert_registration(record)
            if not ok:
                err_text = (db_error if isinstance(db_error, str) else str(db_error or "")).strip()
                if not err_text:
                    err_text = "Please try again or contact support."
                return jsonify({
                    "success": False,
                    "message": "Registration could not be saved to the database. " + err_text
                }), 500
        else:
            db = load_db()
            db.append(record)
            save_db(db)

        print(f"[NEW] {ref} - {record['fullname']} - {plate} - {phone}")

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
        db = load_db()
    return jsonify({
        "success": True,
        "count": len(db),
        "data": db
    })


@app.route("/registration/<ref>", methods=["GET"])
def get_one(ref):
    record = get_registration_by_ref(ref)
    if record is None:
        db = load_db()
        for r in db:
            if r.get("ref") == ref or r.get("id") == ref:
                return jsonify({"success": True, "data": r})
        return jsonify({
            "success": False,
            "message": "Registration not found"
        }), 404
    return jsonify({"success": True, "data": record})


@app.route("/stats", methods=["GET"])
def stats():
    db = load_db_registrations()
    if db is None:
        db = load_db()
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


# Serve the frontend (register.html) with CSS and logo inlined to avoid 404s
@app.route("/", methods=["GET"])
@app.route("/index.html", methods=["GET"])
def serve_frontend():
    import base64
    html_path = os.path.join(BASE_DIR, "register.html")
    css_path = os.path.join(BASE_DIR, "css", "register.css")
    logo_path = os.path.join(BASE_DIR, "assets", "logo.png")
    if not os.path.exists(html_path):
        return "<h2>register.html not found in the same folder as server.py</h2>", 404
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
        html = html.replace('<div class="logo-box"><img src="/assets/logo.png" alt="MotoReg Ethiopia" class="logo-img"></div>',
                            '<div class="logo-box">&#127949;</div>')
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# Serve uploaded files: Supabase Storage or local disk
@app.route("/file/<path:storage_path>")
def serve_drive_file(storage_path):
    """Stream a file from Supabase Storage (stored as 'storage:PATH' in DB)."""
    data, content_type = get_file_from_storage(storage_path)
    if data is None:
        return "File not found", 404
    from flask import Response
    return Response(data, mimetype=content_type)

@app.route("/uploads/<path:filename>")
def serve_uploaded_file(filename):
    # If stored in Supabase Storage (storage:REF/uuid.ext)
    if filename.startswith("storage/"):
        path = filename[8:].strip()
        data, content_type = get_file_from_storage(path)
        if data is None:
            return "File not found", 404
        from flask import Response
        return Response(data, mimetype=content_type)
    return send_from_directory(UPLOAD_DIR, filename)


# ═══════════════════════════════════════════════════════════════
#  ADMIN PANEL ROUTES
# ═══════════════════════════════════════════════════════════════

import hashlib
import functools
from flask import session, redirect, url_for

app.secret_key = os.environ.get("ADMIN_SECRET_KEY", "motoreg-admin-secret-2024")

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

def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/admin", methods=["GET"])
@app.route("/admin.html", methods=["GET"])
def serve_admin():
    admin_path = os.path.join(BASE_DIR, "admin.html")
    if not os.path.exists(admin_path):
        return "<h2>admin.html not found</h2>", 404
    with open(admin_path, "r", encoding="utf-8") as f:
        html = f.read()
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    pin      = (data.get("pin") or "").strip()
    if _check_admin(username, pin):
        session["admin_logged_in"] = True
        session["admin_user"] = username
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
        db = load_db()
    # Build proxy URLs routed through /admin/file/ (authenticated, no public bucket needed)
    for r in db:
        for field in ("licence_file", "idcard_file", "libre_file"):
            val = r.get(field, "")
            if val and val.startswith("storage:"):
                path = val[8:]
                r[f"{field}_url"] = f"/admin/file/{path}"
            elif val and not val.startswith("storage:"):
                r[f"{field}_url"] = f"/{val}"
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
    sb = get_supabase_client()
    if sb:
        try:
            sb.table("registrations").delete().eq("ref", ref).execute()
            return jsonify({"success": True})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "message": str(e)}), 500
    db = load_db()
    before = len(db)
    db = [r for r in db if r.get("ref") != ref and r.get("id") != ref]
    if len(db) == before:
        return jsonify({"success": False, "message": "Record not found"}), 404
    save_db(db)
    return jsonify({"success": True})


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
    sb = get_supabase_client()
    if sb:
        try:
            for ref in refs:
                sb.table("registrations").delete().eq("ref", ref).execute()
            return jsonify({"success": True, "deleted": len(refs)})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "message": str(e)}), 500
    db = load_db()
    ref_set = set(refs)
    before = len(db)
    db = [r for r in db if r.get("ref") not in ref_set and r.get("id") not in ref_set]
    save_db(db)
    return jsonify({"success": True, "deleted": before - len(db)})


@app.route("/admin/update-status", methods=["POST"])
@admin_required
def admin_update_status():
    data   = request.get_json() or {}
    ref    = (data.get("ref") or "").strip()
    status = (data.get("status") or "").strip()
    if not ref or status not in ("approved", "rejected", "pending"):
        return jsonify({"success": False, "message": "Invalid ref or status"}), 400
    sb = get_supabase_client()
    if sb:
        try:
            sb.table("registrations").update({"status": status}).or_(f"ref.eq.{ref},id.eq.{ref}").execute()
            return jsonify({"success": True})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "message": str(e)}), 500
    # JSON fallback
    db = load_db()
    updated = False
    for r in db:
        if r.get("ref") == ref or r.get("id") == ref:
            r["status"] = status
            updated = True
    if updated:
        save_db(db)
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Record not found"}), 404


@app.route("/admin/download-zip", methods=["POST"])
@admin_required
def admin_download_zip():
    """Build a ZIP of driver info (JSON summary) for selected refs."""
    import zipfile, io
    data = request.get_json() or {}
    refs = data.get("refs", [])
    if not refs:
        return jsonify({"success": False, "message": "No refs provided"}), 400

    db = load_db_registrations() or load_db()
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
    """Proxy file from Supabase Storage (authenticated). Used by admin panel thumbnails."""
    data, content_type = get_file_from_storage(storage_path)
    if data is None:
        return "File not found", 404
    from flask import Response
    return Response(data, mimetype=content_type,
                    headers={"Cache-Control": "private, max-age=3600"})


# ── Start ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  MotoReg Ethiopia - Registration Server")
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
    if not get_supabase_client() and not SUPABASE_DATABASE_URL:
        print(f"  Data file  : {DATA_FILE}")
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        print(f"  Files      : Supabase Storage (bucket: {SUPABASE_STORAGE_BUCKET})")
    else:
        print(f"  Uploads    : {UPLOAD_DIR} (local fallback)")
    print("=" * 60)
    print("  Press Ctrl+C to stop\n")

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)