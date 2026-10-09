"""Vercel entrypoint. Vercel's Python runtime looks for an ASGI `app` in this file.

The real code lives in src/app (src layout); this file only makes it importable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from app.main import app

__all__ = ["app"]
