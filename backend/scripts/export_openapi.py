"""Run from repo root; export is generated from the app without starting its lifespan."""

import json
from pathlib import Path

from unified import app

destination = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
destination.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(f"Exported {len(app.openapi()['paths'])} API paths to {destination}")

unified_destination = destination.with_name("openapi-unified.json")
unified_destination.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(f"Exported unified contract to {unified_destination}")
