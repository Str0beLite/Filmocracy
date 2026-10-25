"""Copy the approved public movie snapshot into main's SQLite store; never contact Supabase."""

import argparse
import json
import os
from pathlib import Path

from sqlite_session_store import SessionStore
from tandem import config
from tandem.catalog import Catalog
from tandem.store import Store


def migrate(path, metadata_path):
    path = Path(path)
    existed = path.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    store = Store(path)
    try:
        before = {
            name: store.db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("feeds", "recs", "events", "models")
        }
        rows = json.loads(Path(metadata_path).read_text())
        sessions = SessionStore(store, Catalog.load(), rows)
        with sessions.transaction(write=False) as db:
            saved = {
                (r["provider"], r["provider_movie_id"]): json.loads(r["details"])
                for r in db.execute("SELECT * FROM tandem_movie_metadata")
            }
            assert all((r["provider"], str(r["provider_movie_id"])) in saved for r in rows)
            after = {
                name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in before
            }
            assert before == after, "Existing recommendation records changed"
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            movie_count = db.execute("SELECT COUNT(*) FROM tandem_movies").fetchone()[0]
            mapped = db.execute(
                "SELECT COUNT(*) FROM tandem_movie_metadata WHERE catalog_movie_id IS NOT NULL"
            ).fetchone()[0]
        return {
            "movie_catalog_rows": movie_count,
            "source_metadata_rows": len(rows),
            "supplementary_metadata_rows": len(saved),
            "mapped_to_movielens": mapped,
            "recommendation_counts_before": before,
            "recommendation_counts_after": after,
            "integrity": "ok",
            "foreign_key_errors": 0,
            "supabase_writes": 0,
        }
    finally:
        store.db.close()
        if not existed:
            os.chmod(path, 0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=config.DB_PATH)
    parser.add_argument(
        "--metadata", type=Path, default=config.CATALOG_DIR / "session_movie_metadata.json"
    )
    args = parser.parse_args()
    print(json.dumps(migrate(args.database, args.metadata), indent=2))
