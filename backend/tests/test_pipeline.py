"""End-to-end checks on a synthetic catalog with the fake encoder (no API key, no downloads)."""
import json
import os
import random

os.environ["TANDEM_FAKE_ENCODER"] = "1"

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import torch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tandem import config, vision  # noqa: E402
from tandem.api import create_app  # noqa: E402
from tandem.catalog import Catalog  # noqa: E402
from tandem.encoder import bag  # noqa: E402
from tandem.store import Store  # noqa: E402
from tandem.trainer import Trainer  # noqa: E402

FILLER_TAGS = ["dark comedy", "romance", "paris", "space opera", "aliens", "haunted house", "heist",
               "film noir", "musical", "western", "slow burn", "family drama"]
TARGET_TAGS = ["underdog boxer", "perseverance", "comeback story", "training montage"]
# Feed tags share no words with the target films' tags, so day 0 (W = I) can't connect them; only training can.
GYM_TAGS = ["gym", "deadlift", "protein shakes", "grindset"]


def make_catalog(n_filler=300, n_target=10, seed=0):
    rng = random.Random(seed)
    movies = []
    for i in range(n_filler + n_target):
        target = i >= n_filler
        names = rng.sample(TARGET_TAGS, 3) if target else rng.sample(FILLER_TAGS, 3)
        movies.append({"id": i, "title": f"Underdog {i}" if target else f"Filler {i}",
                       "tags": {t: round(rng.uniform(0.6, 1.0), 2) for t in names}})
    raw = np.stack([bag(m["tags"]) for m in movies])
    return Catalog(movies, raw)


def gym_tags(rng):
    tags = {t: round(rng.uniform(0.5, 1), 2) for t in rng.sample(GYM_TAGS, 3)}
    tags[rng.choice(["memes", "couples", "travel vlog"])] = round(rng.uniform(0.1, 0.4), 2)
    return tags


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CKPT_DIR", tmp_path / "ckpt")
    monkeypatch.setattr(config, "RETRAIN_EVERY", 10_000)  # trigger rounds by hand in tests
    return make_catalog(), Store(tmp_path / "t.db")


def test_untrained_translator_is_identity(setup):
    cat, store = setup
    t = Trainer(store, cat)
    assert torch.allclose(t.model.W(), torch.eye(config.DIM))


def test_api_round_trip_and_live_training(setup):
    cat, store = setup
    rng = random.Random(1)
    targets = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    with TestClient(create_app(catalog=cat, store=store, start_trainer=False)) as c:
        assert c.get("/health").json()["w_version"] == 0

        # Day 0: free-form feed tags already match films by meaning (W = I).
        fid = c.post("/feeds", data={"tags": json.dumps({"dark comedy skits": 1.0, "late night memes": 0.3})}).json()["feed_id"]
        top = c.get(f"/feeds/{fid}/recs").json()["recs"][0]
        assert "dark comedy" in top["tags"] and top["because_of"][0] == "dark comedy skits"

        # Several gym-feed users each love some underdog films and pass on some recs.
        for u in range(8):
            fid = c.post("/feeds", data={"user": f"u{u}", "tags": json.dumps(gym_tags(rng))}).json()["feed_id"]
            recs = c.get(f"/feeds/{fid}/recs").json()["recs"]
            assert len(recs) == config.N_RECS
            for r in recs[:3]:
                c.post("/feedback", json={"rec_id": r["rec_id"], "label": "nah"})
            for idx in rng.sample(targets, 4):
                c.post("/feedback", json={"feed_id": fid, "movie_id": cat.movies[idx]["id"], "label": "love"})

        # A new gym user whose favourites are hidden = the held-out check.
        fid = c.post("/feeds", data={"user": "new", "tags": json.dumps(gym_tags(rng))}).json()["feed_id"]
        fav = c.post(f"/feeds/{fid}/favourites",
                     json={"titles": [cat.movies[i]["title"] for i in targets[:5]], "holdout_frac": 1.0}).json()
        assert len(fav["matched"]) == 5 and all(m["split"] == "holdout" for m in fav["matched"])

        res = c.post("/admin/retrain").json()
        assert res["accepted"] and res["recall_new"] > res["recall_old"], res
        assert c.get("/health").json()["w_version"] == res["version"]

        # The new user (zero feedback of their own) now gets underdog films, credited to their gym tags.
        recs = c.get(f"/feeds/{fid}/recs").json()["recs"]
        hits = [r for r in recs if r["title"].startswith("Underdog")]
        assert hits and set(hits[0]["because_of"]) & set(GYM_TAGS)
        assert len(c.get("/model").json()["history"]) == 1


def test_gate_rejects_a_worse_model(setup):
    cat, store = setup
    trainer = Trainer(store, cat)
    targets = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    feed = {"dark comedy skits": 1.0}
    x = cat.feed_vector(feed)
    comedies = [i for i in range(len(cat.movies)) if "dark comedy" in cat.movies[i]["tags"]]
    # Held-out: a dark-comedy feed loves dark comedies (day 0 already gets this right).
    good = store.add_feed("good", feed, x)
    for i in comedies[:5]:
        store.add_event(good, i, "favourite", 0, split="holdout")
    # A troll with the same feed says comedies are bad and underdog films are great.
    troll = store.add_feed("troll", feed, x)
    for i in comedies:
        store.add_event(troll, i, "nah", 0)
    for i in targets:
        store.add_event(troll, i, "love", 0)
    res = trainer.retrain(steps=200)
    assert res["recall_new"] < res["recall_old"]
    assert not res["accepted"] and trainer.version == 0


def test_checkpoint_reloads_on_restart(setup):
    cat, store = setup
    fid = store.add_feed("u", {"gym": 1.0}, cat.feed_vector({"gym": 1.0}))
    store.add_event(fid, len(cat.movies) - 1, "love", 0)
    t1 = Trainer(store, cat)
    res = t1.retrain()
    t2 = Trainer(store, cat)
    assert t2.version == res["version"]
    assert torch.allclose(t1.model.A, t2.model.A)


def test_screenshots_go_through_llama_and_ads_are_dropped(setup, monkeypatch):
    cat, store = setup

    async def fake_read(shots):
        return [(False, {"gym": 0.9, "brutalist architecture": 0.2}), (True, {"protein ad": 1.0})]

    monkeypatch.setattr(vision, "has_api_key", lambda: True)
    monkeypatch.setattr(vision, "read_screenshots", fake_read)
    with TestClient(create_app(catalog=cat, store=store, start_trainer=False)) as c:
        res = c.post("/feeds", files=[("files", ("a.png", b"\x89PNG", "image/png")),
                                      ("files", ("b.png", b"\x89PNG", "image/png"))]).json()
        assert res["dropped_as_noise"] == 1 and res["tags"] == {"gym": 0.9, "brutalist architecture": 0.2}


def test_llama_reply_parsing_is_tolerant():
    text = '```json\n{"is_ad_or_noise": false, "tags": [{"tag": " Gym  Rat ", "weight": 1.4}, {"tag": "", "weight": 0.5}]}\n```'
    assert vision.parse_reply(text) == (False, {"gym rat": 1.0})
