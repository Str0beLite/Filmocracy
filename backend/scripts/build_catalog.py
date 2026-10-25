"""Build the catalog once, on your laptop: movie tag database -> tag matrix + prior W0.

MovieLens tag genome (ml-25m / ml-32m: movies.csv, genome-tags.csv, genome-scores.csv, optional
links.csv and ratings.csv):

    python scripts/build_catalog.py --genome-dir ~/Downloads/ml-32m --top 5000

Any other tag database as one long CSV with columns movie_id,title,tag,weight (year optional):

    python scripts/build_catalog.py --tags-csv our_movie_tags.csv

Writes catalog/movies.json, movie_tags.json, movie_tag_matrix.npy and w0.npy (commit them all).
The IG vocabulary is catalog/ig_tags.json (edit freely, then rebuild so w0 matches).

W0 is the day-0 guess at W. It comes from tag names: an IG tag points at movie tags that share
words with it ("dark humor" -> "dark comedy", "dark"), plus any pairs you add by hand in
catalog/prior_map.json, e.g. {"gym": ["sports", "underdog", "training"]}. Training corrects it.
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"


def load_genome(d, top):
    d = Path(d).expanduser()
    tags = {}
    with open(d / "genome-tags.csv", newline="") as f:
        for r in csv.DictReader(f):
            tags[int(r["tagId"])] = r["tag"]
    tag_ids = sorted(tags)
    col = {t: i for i, t in enumerate(tag_ids)}

    scores = defaultdict(lambda: np.zeros(len(tag_ids), dtype=np.float32))
    with open(d / "genome-scores.csv", newline="") as f:
        for r in csv.DictReader(f):
            scores[int(r["movieId"])][col[int(r["tagId"])]] = float(r["relevance"])

    meta = {}
    with open(d / "movies.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = re.match(r"^(.*)\s+\((\d{4})\)\s*$", r["title"])
            title, year = (m.group(1), m.group(2)) if m else (r["title"], None)
            meta[int(r["movieId"])] = {"id": int(r["movieId"]), "title": title, "year": year, "genres": r["genres"]}
    if (d / "links.csv").exists():
        with open(d / "links.csv", newline="") as f:
            for r in csv.DictReader(f):
                if int(r["movieId"]) in meta and r.get("tmdbId"):
                    meta[int(r["movieId"])]["tmdb_id"] = int(r["tmdbId"])

    ids = [i for i in scores if i in meta]
    if (d / "ratings.csv").exists() and top:
        print("counting ratings for popularity (ratings.csv is big, give it a minute)")
        counts = Counter()
        with open(d / "ratings.csv", newline="") as f:
            next(f)
            for line in f:
                counts[int(line.split(",", 2)[1])] += 1
        ids.sort(key=lambda i: -counts[i])
        ids = ids[:top]
        for i in ids:
            meta[i]["popularity"] = counts[i]
    elif top:
        ids = ids[:top]
    return [meta[i] for i in ids], [tags[t] for t in tag_ids], np.stack([scores[i] for i in ids])


def load_long_csv(path):
    rows = defaultdict(dict)
    meta, tag_names = {}, {}
    with open(Path(path).expanduser(), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mid = r["movie_id"]
            meta.setdefault(mid, {"id": int(mid) if mid.isdigit() else mid, "title": r["title"], "year": r.get("year")})
            tag = r["tag"].strip().lower()
            tag_names.setdefault(tag, len(tag_names))
            rows[mid][tag] = float(r.get("weight") or 1.0)
    tags = list(tag_names)
    mat = np.zeros((len(meta), len(tags)), dtype=np.float32)
    for i, mid in enumerate(meta):
        for t, w in rows[mid].items():
            mat[i, tag_names[t]] = w
    return list(meta.values()), tags, mat


STOP = {"and", "the", "of", "a", "in", "my", "life", "to"}


def words(tag):
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", tag.lower())} - STOP


def build_prior(ig_tags, movie_tags, manual):
    w0 = np.zeros((len(movie_tags), len(ig_tags)), dtype=np.float32)
    mw = [words(t) for t in movie_tags]
    mindex = {t.lower(): i for i, t in enumerate(movie_tags)}
    for j, ig in enumerate(ig_tags):
        iw = words(ig)
        for i, w in enumerate(mw):
            if iw and w:
                overlap = len(iw & w) / len(iw | w)
                if overlap:
                    w0[i, j] = overlap
        for t in manual.get(ig, []):
            if t.lower() in mindex:
                w0[mindex[t.lower()], j] = 1.0
            else:
                print(f"  prior_map: '{t}' is not a movie tag, skipped")
    norms = np.linalg.norm(w0, axis=0, keepdims=True)
    unmapped = [ig_tags[j] for j in np.where(norms[0] == 0)[0]]
    w0 = w0 / np.maximum(norms, 1e-8)
    return w0, unmapped


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--genome-dir")
    src.add_argument("--tags-csv")
    ap.add_argument("--top", type=int, default=5000, help="keep the N most-rated movies (genome only)")
    ap.add_argument("--out", default=str(CATALOG))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    movies, movie_tags, mat = load_genome(args.genome_dir, args.top) if args.genome_dir else load_long_csv(args.tags_csv)
    print(f"{len(movies)} movies x {len(movie_tags)} movie tags")

    ig_tags = json.loads((CATALOG / "ig_tags.json").read_text())
    manual_path = CATALOG / "prior_map.json"
    manual = json.loads(manual_path.read_text()) if manual_path.exists() else {}
    w0, unmapped = build_prior(ig_tags, movie_tags, manual)
    print(f"W0: {w0.shape}, {len(ig_tags) - len(unmapped)}/{len(ig_tags)} IG tags have a day-0 mapping")
    if unmapped:
        print(f"  no mapping yet (add them to prior_map.json, or let training learn them): {', '.join(unmapped)}")

    if out != CATALOG:
        (out / "ig_tags.json").write_text(json.dumps(ig_tags))
    (out / "movies.json").write_text(json.dumps(movies))
    (out / "movie_tags.json").write_text(json.dumps(movie_tags))
    np.save(out / "movie_tag_matrix.npy", mat.astype(np.float16))
    np.save(out / "w0.npy", w0)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
