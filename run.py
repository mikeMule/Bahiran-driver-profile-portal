#!/usr/bin/env python3
"""
Bahiran Delivery Driver Registration / GebetaDev Team - [MICHAEL] — Application entry point.
Run from project root: python run.py
Loads .env from project root and starts the Flask API (api.app).
"""
from pathlib import Path

# Load .env from project root before importing app
_root = Path(__file__).resolve().parent
_env = _root / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

from api.app import app, PORT

if __name__ == "__main__":
    print("Starting Bahiran API (GebetaDev Team - [MICHAEL])...")
    print(f"  http://localhost:{PORT}/")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
