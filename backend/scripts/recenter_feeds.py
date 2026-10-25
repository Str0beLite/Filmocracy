"""Rebuild every stored feed vector from its saved tags with the current Catalog.feed_vector (centred since 2026-10-25).
Run with the server's TANDEM_DATA_DIR:  PYTHONPATH=backend backend/.venv/bin/python backend/scripts/recenter_feeds.py
Idempotent; safe while the API runs (it reads feeds fresh on every request)."""

import json

import numpy as np

from tandem.catalog import Catalog
from tandem.store import Store


def recenter(store, catalog):
    rows = store._all("SELECT id, tags FROM feeds")
    for row in rows:
        x = catalog.feed_vector(json.loads(row["tags"]))
        store._exec("UPDATE feeds SET x=? WHERE id=?", (x.astype(np.float32).tobytes(), row["id"]))
    return len(rows)


if __name__ == "__main__":
    print(f"recentred {recenter(Store(), Catalog.load())} feeds")
