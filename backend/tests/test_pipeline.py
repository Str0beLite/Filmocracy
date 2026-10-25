"""End-to-end checks on a synthetic tag catalog (no API key, no downloads)."""
import json
import random

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient

from tandem import config, vision
from tandem.api import create_app
from tandem.catalog import Catalog
from tandem.store import Store
from tandem.trainer import Trainer

MOVIE_TAGS = ["underdog", "boxing", "inspirational", "sports", "romance", "paris", "comedy", "funny",
              "space", "aliens", "horror", "creepy", "heist", "noir", "musical", "western"]
FILLER_TAGS = MOVIE_TAGS[4:]
TARGET_TAGS = ["underdog", "boxing", "inspirational", "sports"]
# "gym" has no day-0 mapping, so zero-shot can't connect gym feeds to underdog films; only training can.
IG_TAGS = ["gym", "bodybuilding", "memes", "couples", "nasa", "haunted houses"]


def make_catalog(n_filler=300, n_target=10, seed=0):
    rng = np.random.default_rng(seed)
    col = {t: i for i, t in enumerate(MOVIE_TAGS)}
    raw, movies = [], []
    for i in range(n_filler + n_target):
        v = rng.uniform(0, 0.2, len(MOVIE_TAGS))
        target = i >= n_filler
        for t in (TARGET_TAGS if target else rng.choice(FILLER_TAGS, 3, replace=False)):
            v[col[t]] = rng.uniform(0.7, 1.0)
        raw.append(v)
        movies.append({"id": i, "title": f"Underdog {i}" if target else f"Filler {i}"})
    w0 = np.zeros((len(MOVIE_TAGS), len(IG_TAGS)), dtype=np.float32)
    for ig, mt in [("memes", "comedy"), ("couples", "romance"), ("nasa", "space"), ("haunted houses", "horror")]:
        w0[col[mt], IG_TAGS.index(ig)] = 1.0
    return Catalog(movies, MOVIE_TAGS, IG_TAGS, np.array(raw), w0)


def gym_tags(rng):
    tags = {"gym": round(rng.uniform(0.7, 1), 2), "bodybuilding": round(rng.uniform(0.3, 1), 2)}
    tags[rng.choice(["memes", "couples", "nasa"])] = round(rng.uniform(0.1, 0.4), 2)
    return tags


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CKPT_DIR", tmp_path / "ckpt")
    monkeypatch.setattr(config, "RETRAIN_EVERY", 10_000)  # trigger rounds by hand in tests
    return make_catalog(), Store(tmp_path / "t.db")


def test_untrained_translator_is_the_prior(setup):
    cat, store = setup
    t = Trainer(store, cat)
    assert torch.allclose(t.model.W(), torch.from_numpy(cat.w0))


def test_api_round_trip_and_live_training(setup):
    cat, store = setup
    rng = random.Random(1)
    targets = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    with TestClient(create_app(catalog=cat, store=store, start_trainer=False)) as c:
        assert c.get("/health").json()["w_version"] == 0
        assert c.get("/ig-tags").json() == IG_TAGS

        # Day 0: a "memes" feed already gets comedies through the prior.
        fid = c.post("/feeds", data={"tags": json.dumps({"memes": 1.0})}).json()["feed_id"]
        top = c.get(f"/feeds/{fid}/recs").json()["recs"][0]
        assert "comedy" in top["tags"] and top["because_of"] == ["memes"]

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
        assert hits and "gym" in hits[0]["because_of"]
        assert len(c.get("/model").json()["history"]) == 1


def test_gate_rejects_a_worse_model(setup):
    cat, store = setup
    trainer = Trainer(store, cat)
    targets = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    x = cat.ig_vector({"memes": 1.0})
    comedies = [i for i in range(len(cat.movies)) if "comedy" in cat.top_tags(i, 3)]
    # Held-out: a memes user loves comedies (the prior already gets this right).
    good = store.add_feed("good", {"memes": 1.0}, x)
    for i in comedies[:5]:
        store.add_event(good, i, "favourite", 0, split="holdout")
    # A troll with the same feed says comedies are bad and underdog films are great.
    troll = store.add_feed("troll", {"memes": 1.0}, x)
    for i in comedies:
        store.add_event(troll, i, "nah", 0)
    for i in targets:
        store.add_event(troll, i, "love", 0)
    res = trainer.retrain(steps=200)
    assert res["recall_new"] < res["recall_old"]
    assert not res["accepted"] and trainer.version == 0


def test_checkpoint_reloads_on_restart(setup):
    cat, store = setup
    fid = store.add_feed("u", {"gym": 1.0}, cat.ig_vector({"gym": 1.0}))
    store.add_event(fid, len(cat.movies) - 1, "love", 0)
    t1 = Trainer(store, cat)
    res = t1.retrain()
    t2 = Trainer(store, cat)
    assert t2.version == res["version"]
    assert torch.allclose(t1.model.A, t2.model.A)


def test_screenshots_go_through_llama_and_ads_are_dropped(setup, monkeypatch):
    cat, store = setup

    async def fake_read(shots, ig_tags):
        return [(False, {"gym": 0.9, "memes": 0.2}), (True, {"bodybuilding": 1.0})]

    monkeypatch.setattr(vision, "has_api_key", lambda: True)
    monkeypatch.setattr(vision, "read_screenshots", fake_read)
    with TestClient(create_app(catalog=cat, store=store, start_trainer=False)) as c:
        res = c.post("/feeds", files=[("files", ("a.png", b"\x89PNG", "image/png")),
                                      ("files", ("b.png", b"\x89PNG", "image/png"))]).json()
        assert res["dropped_as_noise"] == 1 and res["ig_tags"] == {"gym": 0.9, "memes": 0.2}


def test_llama_reply_parsing_is_tolerant():
    text = '```json\n{"is_ad_or_noise": false, "tags": [{"tag": "Gym", "weight": 1.4}, {"tag": "made up", "weight": 0.5}]}\n```'
    assert vision.parse_reply(text, IG_TAGS) == (False, {"gym": 1.0})
