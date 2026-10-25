"""Build the catalog once, on your laptop: movie tag database -> each film's tag-embedding vector.

MovieLens tag genome (ml-25m / ml-32m: movies.csv, genome-tags.csv, genome-scores.csv, optional
links.csv and ratings.csv):

    python scripts/build_catalog.py --genome-dir ~/Downloads/ml-32m --top 5000

Any other tag database as one long CSV with columns movie_id,title,tag,weight (year optional):

    python scripts/build_catalog.py --tags-csv our_movie_tags.csv

Any number of tags works on either side: every tag string is embedded, and a film's vector is the
weighted mean of its tags' embeddings. Writes catalog/movies.json and catalog/movie_vecs.npy (commit both).
"""
import argparse
import csv
import math
import re
import sys
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tandem import config  # noqa: E402
from tandem.encoder import embed, unit  # noqa: E402


def load_genome(d, top, k):
    d = Path(d).expanduser()
    with open(d / "genome-tags.csv", newline="") as f:
        tag_name = {int(r["tagId"]): r["tag"] for r in csv.DictReader(f)}
    rel = defaultdict(dict)
    with open(d / "genome-scores.csv", newline="") as f:
        for r in csv.DictReader(f):
            rel[int(r["movieId"])][tag_name[int(r["tagId"])]] = float(r["relevance"])

    meta = {}
    with open(d / "movies.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = re.match(r"^(.*)\s+\((\d{4})\)\s*$", r["title"])
            title, year = (m.group(1), m.group(2)) if m else (r["title"], None)
            meta[int(r["movieId"])] = {"id": int(r["movieId"]), "title": title, "year": year}
    if (d / "links.csv").exists():
        with open(d / "links.csv", newline="") as f:
            for r in csv.DictReader(f):
                if int(r["movieId"]) in meta and r.get("tmdbId"):
                    meta[int(r["movieId"])]["tmdb_id"] = int(r["tmdbId"])

    ids = [i for i in rel if i in meta]
    if (d / "ratings.csv").exists() and top:
        print("counting ratings for popularity (ratings.csv is big, give it a minute)")
        counts = Counter()
        with open(d / "ratings.csv", newline="") as f:
            next(f)
            for line in f:
                counts[int(line.split(",", 2)[1])] += 1
        ids.sort(key=lambda i: -counts[i])
        for i in ids:
            meta[i]["popularity"] = counts[i]
    ids = ids[:top] if top else ids

    # The genome scores every tag for every film; keep each film's strongest k so its vector isn't mush.
    # Tags that are strong for half the catalog ("good", "great movie") still get centred away later.
    movies = []
    for i in ids:
        best = sorted(rel[i].items(), key=lambda kv: -kv[1])[:k]
        movies.append({**meta[i], "tags": {t: round(w, 3) for t, w in best}})
    return movies


def load_long_csv(path):
    meta, tags = {}, defaultdict(dict)
    with open(Path(path).expanduser(), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mid = r["movie_id"]
            meta.setdefault(mid, {"id": int(mid) if mid.isdigit() else mid, "title": r["title"], "year": r.get("year")})
            tags[mid][" ".join(r["tag"].lower().split())] = float(r.get("weight") or 1.0)
    # IDF: a tag on half the catalog says little about a film; a rare one says a lot.
    df = Counter(t for ts in tags.values() for t in ts)
    n = len(meta)
    movies = []
    for mid, m in meta.items():
        movies.append({**m, "tags": {t: round(w * math.log(1 + n / df[t]), 3) for t, w in tags[mid].items()}})
    return movies


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--genome-dir")
    src.add_argument("--tags-csv")
    ap.add_argument("--top", type=int, default=5000, help="keep the N most-rated movies (genome only)")
    ap.add_argument("--tags-per-movie", type=int, default=config.TAGS_PER_MOVIE)
    ap.add_argument("--out", default=str(config.CATALOG_DIR))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    movies = load_genome(args.genome_dir, args.top, args.tags_per_movie) if args.genome_dir else load_long_csv(args.tags_csv)
    all_tags = sorted({t for m in movies for t in m["tags"]})
    print(f"{len(movies)} movies, {len(all_tags)} distinct tags; embedding tags with "
          f"{'fake encoder' if config.FAKE_ENCODER else config.EMBED_MODEL}")
    embed(all_tags)  # one batched pass; bag() below hits the cache

    vecs = np.zeros((len(movies), config.DIM), np.float32)
    for i, m in enumerate(movies):
        names, w = zip(*m["tags"].items())
        vecs[i] = unit((np.asarray(w, np.float32)[:, None] * embed(names)).sum(0))
    np.save(out / "movie_vecs.npy", vecs.astype(np.float16))
    (out / "movies.json").write_text(json.dumps(movies))
    print(f"wrote {out}/movies.json and movie_vecs.npy {vecs.shape}")


if __name__ == "__main__":
    main()
