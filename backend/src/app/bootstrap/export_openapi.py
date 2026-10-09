"""Print the OpenAPI schema as JSON. The frontend generates its API types from it (ADR-009).

uv run python -m app.bootstrap.export_openapi > ../frontend/openapi.json
"""

from __future__ import annotations

import json
import sys

from app.main import app

if __name__ == "__main__":
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
