"""TMDB metadata importer. Dry-run by default; no updates to existing rows."""

import argparse
import json
import os
import re
import time
from datetime import date
from urllib.parse import urlparse

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


def movie_row(details, image_base):
    if details.get("adult") or not str(details.get("title", "")).strip():
        return None
    trailers = [
        video
        for video in details.get("videos", {}).get("results", [])
        if video.get("type") == "Trailer"
        and video.get("site") in ("YouTube", "Vimeo")
        and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(video.get("key", "")))
    ]
    if not trailers:
        return None
    trailers.sort(key=lambda v: (not v.get("official", False), v.get("iso_639_1") != "en"))
    trailer = trailers[0]
    prefix = (
        "https://www.youtube.com/watch?v=" if trailer["site"] == "YouTube" else "https://vimeo.com/"
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
        "trailer_url": prefix + trailer["key"],
        "trailer_provider": trailer["site"].lower(),
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


def insert_movies(client, movies):
    inserted = 0
    for start in range(0, len(movies), 50):
        rows = request(
            client,
            "POST",
            "/rest/v1/movies",
            params={
                "on_conflict": "provider,provider_movie_id",
            },
            headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
            json=movies[start : start + 50],
        )
        inserted += len(rows)
    return {
        "considered": len(movies),
        "inserted": inserted,
        "existing_unchanged": len(movies) - inserted,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument(
        "--write", action="store_true", help="Only after chat approval of source/destination"
    )
    parser.add_argument(
        "--approved-project-ref", help="Must exactly match the approved Supabase hostname"
    )
    args = parser.parse_args()
    if not 100 <= args.count <= 300:
        parser.error("--count must be 100–300")
    # Validate destination and credentials before any remote request on write runs.
    url = os.getenv("CATALOG_SUPABASE_URL", "").rstrip("/")
    secret = os.getenv("CATALOG_SUPABASE_SECRET_KEY", "")
    if args.write and (
        not args.approved_project_ref
        or not secret
        or urlparse(url).scheme != "https"
        or urlparse(url).netloc != f"{args.approved_project_ref}.supabase.co"
    ):
        parser.error(
            "--write requires approved project ref, matching CATALOG_SUPABASE_URL and secret"
        )
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
        headers = {"apikey": secret}
        if secret.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {secret}"
        with httpx.Client(base_url=url, headers=headers, timeout=20) as db:
            print(json.dumps(insert_movies(db, rows)))
    except RuntimeError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
