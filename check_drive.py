#!/usr/bin/env python3
"""
Launcher for Google Drive diagnostic (GebetaDev Team - [MICHAEL]).
Prefer: python -m api.check_drive
"""
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Run the actual check_drive logic from api package
from api import check_drive as _check_drive  # noqa: F401 — runs on import
