"""End-to-end checks with the fake encoder and a synthetic catalog (no API key, no model weights)."""
import os
import random

os.environ["TANDEM_FAKE_ENCODER"] = "1"
os.environ["TANDEM_MIN_VOTES"] = "0"

import pytest  # noqa: E402
import torch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tandem import config  # noqa: E402
from tandem.api import create_app  # noqa: E402
from tandem.catalog import Catalog  # noqa: E402
from tandem.encoder import get_encoder  # noqa: E402
from tandem.model import Translator  # noqa: E402
from tandem.store import Store  # noqa: E402
from tandem.trainer import Trainer  # noqa: E402

# Reels speak creator language, the target films speak critic language: zero words overlap,
# so zero-shot can't connect them and only a learned W can.
REEL_WORDS = ["gym", "lifting", "deadlift", "protein", "pr", "grindset", "reps", "bulk"]
FILM_WORDS = ["underdog", "perseverance", "boxer", "redemption", "triumph", "training", "fighter", "comeback"]
FILLER = ["romance", "paris", "comedy", "wedding", "space", "alien", "heist", "vault", "detective",
          "noir", "horror", "haunted", "musical", "dance", "western", "desert", "spy", "submarine"]


def make_catalog(n_filler=300, n_target=10, seed=0):
    rng = random.Random(seed)
    movies = []
    for i in range(n_filler):
        movies.append({"id": i, "title": f"Filler {i}", "profile": " ".join(rng.sample(FILLER, 4)), "vote_count": 1000})
    for j in range(n_target):
        movies.append({"id": 10_000 + j, "title": f"Underdog {j}",
                       "profile": " ".join(rng.sample(FILM_WORDS, 4)), "vote_count": 1000})
    vecs = get_encoder().encode([m["profile"] for m in movies])
    return Catalog(movies, vecs, {m["id"]: i for i, m in enumerate(movies)})


def gym_feed(rng, n=6):
    return [" ".join(rng.sample(REEL_WORDS, 3)) + " " + rng.choice(FILLER) for _ in range(n)]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CKPT_DIR", tmp_path / "ckpt")
    monkeypatch.setattr(config, "RETRAIN_EVERY", 10_000)  # trigger rounds by hand in tests
    cat = make_catalog()
    store = Store(tmp_path / "t.db")
    return cat, store


def test_untrained_translator_is_zero_shot():
    m = Translator()
    r = torch.nn.functional.normalize(torch.randn(5, config.DIM), dim=-1)
    assert torch.allclose(m(r), r, atol=1e-6)


def test_api_round_trip_and_live_training(setup):
    cat, store = setup
    app = create_app(catalog=cat, store=store, start_trainer=False)
    rng = random.Random(1)
    targets = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    with TestClient(app) as c:
        assert c.get("/health").json()["w_version"] == 0

        # Several gym-feed users each love some underdog films.
        for u in range(8):
            fid = c.post("/feeds", data={"user": f"u{u}", "captions": "\n".join(gym_feed(rng))}).json()["feed_id"]
            recs = c.get(f"/feeds/{fid}/recs").json()["recs"]
            assert len(recs) == config.N_RECS
            assert recs[0]["because_of_reel"]
            for r in recs[:3]:
                c.post("/feedback", json={"rec_id": r["rec_id"], "label": "nah"})
            liked = rng.sample(targets, 4)
            for idx in liked:
                c.post("/feedback", json={"feed_id": fid, "movie_id": cat.movies[idx]["id"], "label": "love"})

        # A new gym user with hidden favourites = the held-out check.
        fid = c.post("/feeds", data={"user": "new", "captions": "\n".join(gym_feed(rng))}).json()["feed_id"]
        fav = c.post(f"/feeds/{fid}/favourites",
                     json={"titles": [cat.movies[i]["title"] for i in targets[:5]], "holdout_frac": 1.0}).json()
        assert len(fav["matched"]) == 5 and all(m["split"] == "holdout" for m in fav["matched"])

        res = c.post("/admin/retrain").json()
        assert res["accepted"], res
        assert res["recall_new"] > res["recall_old"], res
        assert c.get("/health").json()["w_version"] == res["version"]

        # The new user's recs (zero feedback from them) now surface underdog films.
        recs = c.get(f"/feeds/{fid}/recs").json()["recs"]
        assert any(r["title"].startswith("Underdog") for r in recs)
        assert len(c.get("/model").json()["history"]) == 1


def test_gate_rejects_a_worse_model(setup):
    cat, store = setup
    trainer = Trainer(store, cat)
    rng = random.Random(2)
    targets = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    vecs = get_encoder().encode(gym_feed(rng))
    # Held-out user loves underdog films, but the "training" signal (a troll) says the opposite.
    good = store.add_feed("good", [{"summary": "", "profile": ""}] * len(vecs), vecs)
    for i in targets[:3]:
        store.add_event(good, i, "favourite", 0, split="holdout")
    troll = store.add_feed("troll", [{"summary": "", "profile": ""}] * len(vecs), vecs)
    for i in targets:
        store.add_event(troll, i, "nah", 0)
    store.add_event(troll, 0, "love", 0)
    before = trainer.version
    res = trainer.retrain(steps=200)
    if res["recall_new"] < res["recall_old"]:
        assert not res["accepted"] and trainer.version == before
    else:  # recall can't drop below the floor it's already at; then accepting is correct
        assert res["accepted"]


def test_checkpoint_reloads_on_restart(setup):
    cat, store = setup
    rng = random.Random(3)
    vecs = get_encoder().encode(gym_feed(rng))
    fid = store.add_feed("u", [{"summary": "", "profile": ""}] * len(vecs), vecs)
    store.add_event(fid, len(cat.movies) - 1, "love", 0)
    t1 = Trainer(store, cat)
    res = t1.retrain()
    t2 = Trainer(store, cat)
    assert t2.version == res["version"]
    assert torch.allclose(t1.model.A, t2.model.A)


def test_screenshots_go_through_claude_and_ads_are_dropped(setup, monkeypatch):
    from tandem import profiles

    cat, store = setup

    async def fake_profile_reels(shots, caps):
        base = dict(mood="gritty", themes="grind", aesthetic="gym", pacing="fast", setting="gym", who_loves_this="lifters")
        return [profiles.ReelProfile(**base, is_ad_or_noise=False, caption_summary="deadlift PR"),
                profiles.ReelProfile(**base, is_ad_or_noise=True, caption_summary="protein ad")]

    monkeypatch.setattr(profiles, "has_api_key", lambda: True)
    monkeypatch.setattr(profiles, "profile_reels", fake_profile_reels)
    with TestClient(create_app(catalog=cat, store=store, start_trainer=False)) as c:
        res = c.post("/feeds", files=[("files", ("a.png", b"\x89PNG", "image/png")),
                                      ("files", ("b.png", b"\x89PNG", "image/png"))]).json()
        assert res["dropped_as_noise"] == 1 and [r["summary"] for r in res["reels"]] == ["deadlift PR"]
