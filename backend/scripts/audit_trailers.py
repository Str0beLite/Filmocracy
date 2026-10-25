"""Read-only audit. Input is a JSON export of public.movies; never edits either catalog."""

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
from session_recommendations import movie_mapping, verify_trailer, youtube_id


async def audit(rows, movies):
    catalog = type("Catalog", (), {"movies": movies})()
    mapping = movie_mapping(catalog, rows)
    semaphore = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=10) as client:

        async def check(row):
            async with semaphore:
                result = {
                    "movie_id": movies[mapping[row.get("id", row.get("source_id"))]]["id"],
                    "source_id": row.get("source_id", row.get("id")),
                    "youtube_id": youtube_id(row),
                    "playback": "unverified",
                }
                if not result["youtube_id"]:
                    result["metadata"] = "invalid_url"
                    return result
                try:
                    response = await client.get(
                        "https://www.youtube.com/oembed",
                        params={"url": row["trailer_url"], "format": "json"},
                    )
                    result["metadata"] = (
                        "available"
                        if response.status_code == 200
                        else f"http_{response.status_code}"
                    )
                    if response.status_code == 200:
                        data = response.json()
                        result["metadata"] = (
                            "available" if data.get("type") == "video" else "unexpected_response"
                        )
                except (httpx.HTTPError, ValueError):
                    result["metadata"] = "network_error"
                if os.getenv("YOUTUBE_API_KEY"):
                    try:
                        result["playback"] = (
                            "provider_verified"
                            if await verify_trailer(client, row)
                            else "excluded_by_provider"
                        )
                    except (httpx.HTTPError, ValueError):
                        result["playback"] = "verification_error"
                return result

        results = await asyncio.gather(
            *(check(r) for r in rows if r.get("id", r.get("source_id")) in mapping)
        )
    return {
        "overlap": len(mapping),
        "provider_verified": sum(r["playback"] == "provider_verified" for r in results),
        "note": (
            "Provider checks apply to TRAILER_REGION (default US); "
            "test actual TV playback separately."
        ),
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rows", type=Path)
    parser.add_argument("--catalog", type=Path, default=Path("backend/catalog/movies.json"))
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                audit(json.loads(args.rows.read_text()), json.loads(args.catalog.read_text()))
            ),
            indent=2,
        )
    )
