"""Fill the running API with fake users so W has something to learn from before real people arrive.

Each persona pairs Instagram-style feed tags with the catalog tags of films that person actually likes. The feed
tags deliberately don't name the film tags ("deadlift" -> sports films), so day-0 W = I gets them only partly right
and training has a real link to learn. Every fake user id starts with "fake-", so the data can be dropped later.

    python scripts/seed_fake.py                    # 60 users against localhost:8000 (needs TANDEM_DEV_AUTH=1)
    python scripts/seed_fake.py --users 120 --seed 7
"""
import argparse
import json
import random
from pathlib import Path

import requests

# name: (feed tags, film tags they love, film tags they dislike). Film tags are real tags from catalog/movies.json.
PERSONAS = {
    "gym": (["gym", "deadlift", "protein shakes", "meal prep", "ufc highlights", "morning motivation", "bodybuilding",
             "running club"],
            ["sports", "martial arts", "fight scenes", "action packed", "good action", "revenge", "fighting"],
            ["chick flick", "musical", "talky", "girlie movie"]),
    "girlie": (["skincare routine", "outfit of the day", "met gala looks", "taylor swift", "iced coffee", "brunch",
                "nail art", "pilates"],
               ["romantic comedy", "chick flick", "love story", "feel-good", "girlie movie", "good romantic comedies"],
               ["gory", "splatter", "war", "brutality"]),
    "truecrime": (["true crime podcasts", "cold case files", "forensics", "unsolved mysteries", "courtroom clips",
                   "internet sleuths"],
                  ["serial killer", "police investigation", "murder mystery", "detective", "psychological", "twist ending"],
                  ["kids", "musical", "silly fun", "talking animals"]),
    "anime": (["anime edits", "manga panels", "cosplay", "japanese street food", "ghibli fan art", "lofi beats"],
              ["animation", "japan", "fantasy world", "imagination", "dreams", "dark fantasy"],
              ["chick flick", "sports", "politics"]),
    "cinephile": (["letterboxd reviews", "a24", "film photography", "criterion closet", "director interviews",
                   "35mm film"],
                  ["criterion", "cinematography", "independent film", "cerebral", "character study", "existentialism",
                   "surreal"],
                  ["franchise", "big budget", "predictable", "dumb"]),
    "space": (["rocket launches", "astrophysics memes", "telescope photos", "nasa", "physics explainers",
               "mars rovers"],
              ["space", "sci-fi", "first contact", "space travel", "aliens", "futuristic"],
              ["chick flick", "musical", "period piece"]),
    "horror": (["haunted houses", "creepypasta", "halloween decor", "paranormal investigations", "tarot",
                "abandoned places"],
               ["horror", "ghosts", "supernatural", "creepy", "slasher", "demons", "scary"],
               ["feel-good", "chick flick", "kids and family"]),
    "parent": (["toddler milestones", "family road trips", "disney parks", "baking with kids", "minivan life",
                "bedtime stories"],
               ["disney", "kids and family", "talking animals", "animated", "heartwarming", "family"],
               ["violence", "gory", "nudity (topless - notable)", "sexual"]),
    "history": (["world war 2 documentaries", "castles", "roman empire memes", "medieval swords", "old maps",
                 "museum visits"],
                ["war", "world war ii", "historical", "period piece", "biographical", "wartime"],
                ["teen movie", "silly", "chick flick"]),
    "street": (["sneaker drops", "rap battles", "streetwear", "nba highlights", "luxury cars", "drill music"],
               ["gangsters", "organized crime", "hip hop", "heist", "mob", "crime"],
               ["period piece", "musical", "fairy tale"]),
    "memes": (["shitposts", "stand-up clips", "snl sketches", "reaction memes", "prank videos", "cursed images"],
              ["comedy", "hilarious", "parody", "spoof", "slapstick", "dumb but funny", "saturday night live"],
              ["bleak", "depression", "melancholic", "talky"]),
    "sadindie": (["rainy window aesthetic", "poetry", "vinyl records", "thrift hauls", "journaling", "indie folk"],
                 ["melancholic", "bittersweet", "coming of age", "loneliness", "independent film", "reflective"],
                 ["action packed", "explosions", "franchise"]),
    "gamer": (["pc builds", "speedruns", "esports", "coding memes", "retro consoles", "rgb setups"],
              ["technology", "geeks", "alternate reality", "dystopia", "computer animation", "futuristic"],
              ["chick flick", "period piece", "family drama"]),
    "outdoors": (["hiking", "van life", "national parks", "surfing", "rock climbing", "camping"],
                 ["survival", "adventure", "beautiful scenery", "road trip", "scenic", "jungle"],
                 ["claustrophobic", "talky", "girlie movie"]),
}


POP_PULL = 0.9


def make_user(rng, i):
    """Pick one persona (or two, 30% of the time) and sample a noisy feed from them."""
    names = rng.sample(sorted(PERSONAS), 2 if rng.random() < 0.3 else 1)
    feed, love, hate = {}, set(), set()
    for k, n in enumerate(names):
        tags, lv, ht = PERSONAS[n]
        for t in rng.sample(tags, rng.randint(4, len(tags))):
            feed[t] = round(rng.uniform(0.5, 1.0) * (1 if k == 0 else 0.7), 2)
        love |= set(lv)
        hate |= set(ht)
    noise = rng.choice([t for n in PERSONAS if n not in names for t in PERSONAS[n][0]])
    feed[noise] = round(rng.uniform(0.2, 0.4), 2)   # everyone's feed has one off-taste thing in it
    return f"fake-{'-'.join(names)}-{i}", feed, love, hate - love


def taste(movie, love, hate):
    """Ground truth for this fake person: love-tag weight minus hate-tag weight, plus a pull toward the hits.

    Most people like the top films whatever their feed says: the most-rated film gets +0.9 (a "love" alone),
    the 90th percentile about +0.6, and the median film almost nothing.
    """
    tags = movie["tags"]
    return (sum(tags.get(t, 0) for t in love) - sum(tags.get(t, 0) for t in hate)
            + POP_PULL * movie["pop_pct"] ** 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=60)
    ap.add_argument("--rounds", type=int, default=3, help="rec lists each user rates")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    movies = json.loads((Path(__file__).resolve().parent.parent / "catalog" / "movies.json").read_text())
    for rank, m in enumerate(sorted(movies, key=lambda m: m.get("popularity", 0))):
        m["pop_pct"] = rank / (len(movies) - 1)

    for i in range(a.users):
        uid, feed, love, hate = make_user(rng, i)
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {uid}"

        def call(method, path, s=s, **kw):
            r = s.request(method, a.api + path, timeout=120, **kw)
            r.raise_for_status()
            return r.json()

        fid = call("POST", "/feeds", data={"tags": json.dumps(feed)})["feed_id"]
        # Favourites: their best-scoring films, so a mix of on-taste picks and big hits (about 30% get hidden for the recall check).
        best = sorted(movies, key=lambda m: -taste(m, love, hate))[:80]
        favs = rng.sample(best, 8)
        call("POST", f"/feeds/{fid}/favourites", json={"movie_ids": [m["id"] for m in favs]})

        n_love = n_nah = 0
        by_id = {m["id"]: m for m in movies}
        for _ in range(a.rounds):
            for r in call("GET", f"/feeds/{fid}/recs")["recs"]:
                if rng.random() < 0.2:
                    continue                                   # "don't know it"
                score = taste(by_id[r["id"]], love, hate) + rng.gauss(0, 0.1)   # people are a bit random
                label = "love" if score > 0.6 else "nah" if score < 0.3 else None
                if label:
                    call("POST", "/feedback", json={"rec_id": r["rec_id"], "label": label})
                    n_love += label == "love"
                    n_nah += label == "nah"
        print(f"{uid:32} {len(feed)} feed tags, 8 favourites, {n_love} loved, {n_nah} nah")

    print(json.dumps(requests.get(a.api + "/health", timeout=30).json()))


if __name__ == "__main__":
    main()
