"""Rate recs in the terminal to test the algorithm and feed W training data, no frontend needed.

Needs the API running (the name you pass is your user id):
    python scripts/play.py alice                         # reuse alice's latest feed, or make one
    python scripts/play.py alice --new                   # type a fresh set of feed tags
    python scripts/play.py alice --shots a.png b.png     # read screenshots with Muse Spark (needs MUSE_API_KEY)
    python scripts/play.py alice --boost heist           # push films with a tag up, like the host's mood pick
Keys while rating: y/s/f/n, enter to skip, +title to favourite any film, q to quit.
"""
import argparse
import json
import mimetypes
from pathlib import Path

import requests

KEYS = {"y": "love", "s": "seen_loved", "n": "nah"}


def parse_tags(line):
    """'dark humor:1, gym:0.6, cozy' -> {tag: weight}; a tag without a weight gets 1."""
    tags = {}
    for part in filter(None, (p.strip() for p in line.split(","))):
        tag, _, w = part.rpartition(":") if ":" in part else (part, "", "1")
        tags[tag.strip()] = float(w)
    return tags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--new", action="store_true", help="make a new feed even if you have one")
    ap.add_argument("--shots", nargs="*", default=[], help="feed screenshots to read with Muse Spark")
    ap.add_argument("--boost", nargs="*", default=[])
    a = ap.parse_args()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {a.name}"

    def call(method, path, **kw):
        r = s.request(method, a.api + path, timeout=120, **kw)
        if not r.ok:
            raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text}")
        return r.json()

    fid = None if a.new or a.shots else call("GET", "/me")["feed_id"]
    if not fid:
        tags = {} if a.shots else parse_tags(input("Your feed as tags (e.g. 'dark humor:1, gym:0.6, cozy'): "))
        files = [("files", (Path(p).name, Path(p).read_bytes(), mimetypes.guess_type(p)[0] or "image/png")) for p in a.shots]
        feed = call("POST", "/feeds", data={"tags": json.dumps(tags)}, files=files or None)
        fid = feed["feed_id"]
        print("feed tags:", ", ".join(f"{t} {w}" for t, w in feed["tags"].items()))
        favs = input("Films you already love, comma-separated (enter to skip): ")
        if favs.strip():
            res = call("POST", f"/feeds/{fid}/favourites", json={"titles": [t.strip() for t in favs.split(",")]})
            print("matched:", ", ".join(m["title"] for m in res["matched"]) or "none",
                  "| not found:", ", ".join(res["missing"]) or "none")

    def favourite(movie_id):
        res = call("POST", f"/feeds/{fid}/favourites", json={"movie_ids": [movie_id]})
        for m in res["matched"]:
            print(f"  ★ {m['title']} saved as a favourite ({m['split']})")

    def add_by_title(q):
        hits = call("GET", "/movies/search", params={"q": q, "limit": 5})
        if not hits:
            return print(f"  no film matching '{q}'")
        for i, m in enumerate(hits, 1):
            print(f"  {i}. {m['title']} ({m['year']})")
        pick = input("  which one? (number, enter to cancel) ").strip()
        if pick.isdigit() and 1 <= int(pick) <= len(hits):
            favourite(hits[int(pick) - 1]["id"])

    print("\n[y] want to watch  [s] seen it, loved it  [f] loved it, save as favourite  [n] nah"
          "  [enter] don't know it  [+title] add any film as a favourite  [q] quit\n")
    seen = set()
    while True:
        out = call("GET", f"/feeds/{fid}/recs", params={"boost": a.boost})
        fresh = [r for r in out["recs"] if r["id"] not in seen]
        if not fresh:
            raise SystemExit("Nothing new to rate. Rate some with y/s/f/n so the list moves on.")
        print(f"--- W v{out['w_version']} ---")
        for r in fresh:
            seen.add(r["id"])
            why = ", ".join(r["because_of"][:3])
            key = "+"
            while key.startswith("+"):   # +title doesn't rate this rec, so ask again afterwards
                key = input(f"{r['title']} ({r['year']})  score {r['score']:.2f}  because: {why}\n  > ").strip()
                if key.startswith("+"):
                    add_by_title(key[1:].strip())
            key = key.lower()
            if key == "f":
                favourite(r["id"])
            if key == "q":
                m = call("GET", "/model")
                print(f"bye. W v{m['w_version']}, {len(m['history'])} retrain rounds so far.")
                return
            if key in KEYS:
                res = call("POST", "/feedback", json={"rec_id": r["rec_id"], "label": KEYS[key]})
                print(f"  {KEYS[key]} ({res['events']} events total)")


if __name__ == "__main__":
    main()
