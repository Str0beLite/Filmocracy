"""TMDB metadata importer. Dry-run by default; no updates to existing rows."""

import argparse
import json
import os
import re
import sqlite3
import time
from datetime import date
from pathlib import Path

import httpx


def request(client, method, path, *, sleep=time.sleep, **kwargs):
    for attempt in range(4):
        try:
            response = client.request(method, path, **kwargs)
        except httpx.RequestError:
            if attempt == 3:
                raise RuntimeError("Upstream network unavailable; import stopped") from None
            sleep(2**attempt)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < 3:
                retry_after = response.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdigit() else 2**attempt
                sleep(min(delay, 30))
                continue
        if response.is_error:
            raise RuntimeError(f"Upstream returned HTTP {response.status_code}; import stopped")
        return response.json() if response.content else None
    raise RuntimeError("Retry budget exhausted")


def movie_row(details, image_base, require_trailer=True):
    if details.get("adult") or not str(details.get("title", "")).strip():
        return None
    trailers = [
        video
        for video in details.get("videos", {}).get("results", [])
        if video.get("type") == "Trailer"
        and video.get("site") in ("YouTube", "Vimeo")
        and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(video.get("key", "")))
    ]
    if not trailers and require_trailer:
        return None
    trailers.sort(key=lambda v: (not v.get("official", False), v.get("iso_639_1") != "en"))
    trailer = trailers[0] if trailers else None
    prefix = (
        "https://www.youtube.com/watch?v=" if trailer and trailer["site"] == "YouTube" else "https://vimeo.com/"
    )
    try:
        release_date = date.fromisoformat(details.get("release_date", "")).isoformat()
    except (ValueError, TypeError):
        release_date = None
    runtime = details.get("runtime")
    poster = details.get("poster_path")
    return {
        "provider": "tmdb",
        "provider_movie_id": str(details["id"]),
        "title": details["title"],
        "overview": details.get("overview") or None,
        "poster_url": image_base + "w500" + poster if poster and poster.startswith("/") else None,
        "release_date": release_date,
        "runtime_minutes": runtime if isinstance(runtime, int) and runtime > 0 else None,
        "genres": [g["name"] for g in details.get("genres", []) if g.get("name")],
        "trailer_url": prefix + trailer["key"] if trailer else None,
        "trailer_provider": trailer["site"].lower() if trailer else None,
    }


def collect_movies(client, count, *, sleep=time.sleep):
    if not 100 <= count <= 300:
        raise ValueError("count must be between 100 and 300")
    configuration = request(client, "GET", "/configuration", sleep=sleep)
    image_base = configuration["images"]["secure_base_url"]
    if not image_base.startswith("https://"):
        raise RuntimeError("TMDB returned an insecure image base URL")
    movies, seen = [], set()
    for page in range(1, 101):
        data = request(
            client,
            "GET",
            "/discover/movie",
            sleep=sleep,
            params={
                "include_adult": "false",
                "include_video": "false",
                "language": "en-US",
                "sort_by": "popularity.desc",
                "primary_release_date.lte": date.today().isoformat(),
                "page": page,
            },
        )
        for candidate in data.get("results", []):
            if candidate["id"] in seen:
                continue
            seen.add(candidate["id"])
            sleep(0.1)
            details = request(
                client,
                "GET",
                f"/movie/{candidate['id']}",
                sleep=sleep,
                params={"append_to_response": "videos", "language": "en-US"},
            )
            row = movie_row(details, image_base)
            if row:
                movies.append(row)
            if len(movies) == count:
                return movies
        if page >= data.get("total_pages", 0):
            break
    raise RuntimeError(f"Only {len(movies)} trailer-bearing movies found; no database writes made")


def insert_movies(database, movies):
    """Insert public metadata only, without changing main's catalog or existing rows."""
    from sqlite_session_store import SessionStore
    from tandem.catalog import Catalog
    from tandem.store import Store

    store = Store(Path(database))
    try:
        before = store.db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='tandem_movie_metadata'"
        ).fetchone()[0]
        count = (
            store.db.execute("SELECT COUNT(*) FROM tandem_movie_metadata").fetchone()[0]
            if before
            else 0
        )
        SessionStore(store, Catalog.load(), movies)
        after = store.db.execute("SELECT COUNT(*) FROM tandem_movie_metadata").fetchone()[0]
        return {
            "considered": len(movies),
            "inserted": after - count,
            "existing_unchanged": len(movies) - (after - count),
        }
    finally:
        store.db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument(
        "--write", action="store_true", help="Only after chat approval of source/destination"
    )
    parser.add_argument(
        "--database", type=Path, help="Approved SQLite destination, required with --write"
    )
    args = parser.parse_args()
    if not 100 <= args.count <= 300:
        parser.error("--count must be 100–300")
    if args.write and not args.database:
        parser.error("--write requires an explicitly approved --database path")
    token = os.getenv("TMDB_READ_ACCESS_TOKEN")
    if not token:
        parser.error("Set TMDB_READ_ACCESS_TOKEN in the environment")
    try:
        with httpx.Client(
            base_url="https://api.themoviedb.org/3",
            timeout=20,
            headers={"Authorization": f"Bearer {token}"},
        ) as tmdb:
            rows = collect_movies(tmdb, args.count)
        if not args.write:
            print(
                json.dumps(
                    {
                        "mode": "dry-run",
                        "source": "TMDB",
                        "count": len(rows),
                        "trailers": "metadata-listed YouTube/Vimeo trailers",
                        "writes": 0,
                    }
                )
            )
            return
        print(json.dumps(insert_movies(args.database, rows)))
    except (RuntimeError, sqlite3.Error) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
