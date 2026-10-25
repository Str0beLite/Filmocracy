"""Store TMDB details (title, poster, overview, genres, runtime, trailer when there is one) for the top films, so screens
show posters right away. Films outside it still work: screens look their trailer up live by tmdb_id.
Run:  TMDB_READ_ACCESS_TOKEN=... PYTHONPATH=backend backend/.venv/bin/python backend/scripts/prefill_movies.py [--top 5000]
Writes catalog/session_movie_metadata.json (existing rows kept as they are); the server loads new rows on its next start."""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
from import_tmdb import movie_row, request
from tandem import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5000)
    top = ap.parse_args().top
    path = config.CATALOG_DIR / "session_movie_metadata.json"
    rows = json.loads(path.read_text())
    have = {r["provider_movie_id"] for r in rows if r["provider"] == "tmdb"}
    movies = json.loads((config.CATALOG_DIR / "movies.json").read_text())[:top]
    todo = [str(m["tmdb_id"]) for m in movies if m.get("tmdb_id") and str(m["tmdb_id"]) not in have]
    with httpx.Client(
        base_url="https://api.themoviedb.org/3",
        timeout=20,
        headers={"Authorization": f"Bearer {os.environ['TMDB_READ_ACCESS_TOKEN']}"},
    ) as tmdb:
        image_base = request(tmdb, "GET", "/configuration")["images"]["secure_base_url"]

        def fetch(tmdb_id):
            try:
                details = request(
                    tmdb, "GET", f"/movie/{tmdb_id}", params={"append_to_response": "videos", "language": "en-US"}
                )
            except RuntimeError:  # a film TMDB dropped; screens fall back to the catalog title
                return None
            return movie_row(details, image_base, require_trailer=False) if details else None

        with ThreadPoolExecutor(8) as pool:
            found = [r for r in pool.map(fetch, todo) if r]
    next_id = max((r.get("source_id") or 0 for r in rows), default=0) + 1
    rows += [{"source_id": next_id + i, **row} for i, row in enumerate(found)]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    print(f"looked up {len(todo)} films, stored {len(found)}; {len(rows)} rows in {path.name}")


if __name__ == "__main__":
    main()
