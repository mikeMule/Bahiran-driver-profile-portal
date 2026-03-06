#!/usr/bin/env python3
"""
Run this on your VPS to diagnose Google Drive access.
Usage: python check_drive.py
"""
import os, json, sys

CREDS_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "./service-account-drive.json")
FOLDER_ID  = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()

print("=" * 60)
print("  MotoReg Drive Diagnostic")
print("=" * 60)

# ── 1. Load credentials ───────────────────────────────────────
if not os.path.isfile(CREDS_FILE):
    print(f"[ERROR] Credentials file not found: {CREDS_FILE}")
    sys.exit(1)
print(f"[OK] Credentials file found: {CREDS_FILE}")

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:
    print("[ERROR] Missing library. Run:  pip install google-api-python-client google-auth")
    sys.exit(1)

creds   = service_account.Credentials.from_service_account_file(
    CREDS_FILE, scopes=["https://www.googleapis.com/auth/drive"]
)
service = build("drive", "v3", credentials=creds)
print(f"[OK] Authenticated as: {creds.service_account_email}")

# ── 2. List all Shared Drives the service account can see ────
print("\n--- Shared Drives visible to service account ---")
try:
    result = service.drives().list(pageSize=20).execute()
    drives = result.get("drives", [])
    if not drives:
        print("[WARN] No Shared Drives found!")
        print("       → You need to create a Shared Drive and add the service account as a member.")
    for d in drives:
        print(f"  Shared Drive: {d['name']}  (id={d['id']})")
        print(f"  ✅ Use this as GOOGLE_DRIVE_FOLDER_ID={d['id']}")
except Exception as e:
    print(f"[ERROR] Could not list Shared Drives: {e}")

# ── 3. Check the currently configured folder ─────────────────
if FOLDER_ID:
    print(f"\n--- Checking configured GOOGLE_DRIVE_FOLDER_ID={FOLDER_ID} ---")
    try:
        meta = service.files().get(
            fileId=FOLDER_ID,
            fields="id,name,mimeType,driveId,parents",
            supportsAllDrives=True
        ).execute()
        name     = meta.get("name")
        drive_id = meta.get("driveId")
        mime     = meta.get("mimeType")
        print(f"  Name    : {name}")
        print(f"  MimeType: {mime}")
        if drive_id:
            print(f"  driveId : {drive_id}")
            print(f"  ✅ This is inside a Shared Drive — uploads WILL work!")
        else:
            print(f"  driveId : (none) — this is in MY DRIVE")
            print(f"  ❌ Uploads will FAIL. Move this folder to a Shared Drive.")
    except Exception as e:
        print(f"[ERROR] Could not fetch folder metadata: {e}")
else:
    print("\n[WARN] GOOGLE_DRIVE_FOLDER_ID is not set in .env")
    print("       → Set it to a Shared Drive ID from the list above.")

# ── 4. Quick upload test ──────────────────────────────────────
print("\n--- Upload test ---")
if not FOLDER_ID:
    print("[SKIP] No GOOGLE_DRIVE_FOLDER_ID set.")
else:
    try:
        import tempfile
        from googleapiclient.http import MediaFileUpload
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w") as f:
            f.write("MotoReg drive test file")
            tmp = f.name
        meta = {"name": "_motorg_test_.txt", "parents": [FOLDER_ID]}
        media = MediaFileUpload(tmp, mimetype="text/plain", resumable=False)
        result = service.files().create(
            body=meta, media_body=media, fields="id",
            supportsAllDrives=True
        ).execute()
        file_id = result.get("id")
        print(f"  ✅ Upload SUCCESS! File id={file_id}")
        print(f"     Cleaning up test file...")
        service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        print(f"  ✅ Test file deleted. Drive is fully configured!")
        os.unlink(tmp)
    except Exception as e:
        print(f"  ❌ Upload FAILED: {e}")
        print(f"     This confirms the folder is not in a Shared Drive.")

print("\n" + "=" * 60)
print("  Done. Follow the instructions above to fix the issue.")
print("=" * 60)