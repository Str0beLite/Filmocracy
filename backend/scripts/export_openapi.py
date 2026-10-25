"""Run from repo root; export is generated from the app without starting its lifespan."""

import json
from pathlib import Path

from app import app

destination = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
destination.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(f"Exported {len(app.openapi()['paths'])} API paths to {destination}")
