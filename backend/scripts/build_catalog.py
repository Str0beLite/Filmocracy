"""Build the movie catalog once, on your laptop: TMDB 5000 CSV -> taste profiles -> embeddings.

    python scripts/build_catalog.py --csv ~/Downloads/tmdb_5000_movies.csv

Writes catalog/movies.json and catalog/movie_vecs.npy (commit both). Profiles are cached in
catalog/profiles.jsonl, so a crashed run resumes where it stopped. --no-llm skips Claude and embeds
raw metadata instead (works, but expect worse matches).
"""
import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tandem import config, profiles  # noqa: E402
from tandem.encoder import get_encoder  # noqa: E402


def names(cell):
    try:
        return ", ".join(x["name"] for x in json.loads(cell or "[]"))
    except json.JSONDecodeError:
        return ""


def load_csv(path, limit, min_votes):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    movies = []
    for r in rows:
        votes = int(float(r.get("vote_count") or 0))
        if votes < min_votes or not (r.get("overview") or "").strip():
            continue
        movies.append({
            "id": int(r["id"]), "title": r["title"], "year": (r.get("release_date") or "")[:4],
            "overview": r["overview"], "genres": names(r.get("genres")), "keywords": names(r.get("keywords")),
            "tagline": r.get("tagline", ""), "vote_count": votes,
        })
    movies.sort(key=lambda m: -m["vote_count"])
    return movies[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default=str(config.CATALOG_DIR))
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--min-votes", type=int, default=50)
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    movies = load_csv(args.csv, args.limit, args.min_votes)
    print(f"{len(movies)} movies")

    cache_path = out / "profiles.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            row = json.loads(line)
            cache[row["id"]] = row["profile"]

    if not args.no_llm:
        if not profiles.has_api_key():
            sys.exit("Set ANTHROPIC_API_KEY, or pass --no-llm")
        todo = [m for m in movies if m["id"] not in cache]
        print(f"writing {len(todo)} taste profiles with {config.PROFILE_MODEL} ({len(cache)} cached)")
        done = [0]
        with open(cache_path, "a") as fh:
            def on_done(m, p):
                done[0] += 1
                if p is not None:
                    cache[m["id"]] = p.to_text()
                    fh.write(json.dumps({"id": m["id"], "profile": cache[m["id"]]}) + "\n")
                    fh.flush()
                if done[0] % 100 == 0:
                    print(f"  {done[0]}/{len(todo)}")
            asyncio.run(profiles.profile_movies(todo, on_done=on_done))

    for m in movies:
        m["profile"] = cache.get(m["id"]) if not args.no_llm else None
        m["profile"] = m["profile"] or profiles.raw_movie_text(m)

    print(f"embedding with {config.EMBED_MODEL}")
    vecs = get_encoder().encode([m["profile"] for m in movies])
    np.save(out / "movie_vecs.npy", vecs.astype(np.float16))
    (out / "movies.json").write_text(json.dumps(
        [{k: m[k] for k in ("id", "title", "year", "overview", "genres", "vote_count", "profile")} for m in movies]))
    print(f"wrote {out}/movies.json and movie_vecs.npy {vecs.shape}")


if __name__ == "__main__":
    main()
