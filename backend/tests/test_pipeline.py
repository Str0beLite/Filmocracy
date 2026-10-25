"""End-to-end checks on a synthetic catalog with the fake encoder (no API key, no downloads)."""
import asyncio
import json
import os
import random

os.environ["TANDEM_FAKE_ENCODER"] = "1"

import numpy as np
import pytest
import torch
from fastapi import Header
from fastapi.testclient import TestClient

from tandem import config, vision
from tandem.api import create_app
from tandem.auth import current_user
from tandem.catalog import Catalog
from tandem.encoder import bag
from tandem.model import Translator, from_state, loss_fn, state
from tandem.recommend import boost, score_feed
from tandem.store import Store
from tandem.trainer import Trainer

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


def client(cat, store):
    """Test client where `Authorization: Bearer <name>` signs in as <name> (default "anon")."""
    app = create_app(catalog=cat, store=store, start_trainer=False)
    def fake_user(authorization: str = Header("anon")):
        return authorization.removeprefix("Bearer ")

    app.dependency_overrides[current_user] = fake_user
    return TestClient(app)


def as_(user):
    return {"Authorization": f"Bearer {user}"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CKPT_DIR", tmp_path / "ckpt")
    monkeypatch.setattr(config, "RETRAIN_EVERY", 10_000)  # trigger rounds by hand in tests
    monkeypatch.setattr(config, "ADMIN_TOKEN", "admin")
    monkeypatch.setattr(config, "SEED_W", tmp_path / "no_seed.pt")  # tests start from W = I
    return make_catalog(), Store(tmp_path / "t.db")


def test_untrained_translator_is_identity(setup):
    cat, store = setup
    t = Trainer(store, cat)
    assert torch.allclose(t.model.W(), torch.eye(config.DIM))


def test_fresh_database_starts_from_seed_w(setup, tmp_path, monkeypatch):
    cat, store = setup
    seed = Translator(cat.w0)
    with torch.no_grad():
        seed.A.normal_()
        seed.B.normal_()
    torch.save(state(seed), tmp_path / "seed.pt")
    monkeypatch.setattr(config, "SEED_W", tmp_path / "seed.pt")
    t = Trainer(store, cat)
    assert t.version == 0 and torch.allclose(t.model.W(), seed.W())


def test_api_round_trip_and_live_training(setup):
    cat, store = setup
    rng = random.Random(1)
    targets = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    with client(cat, store) as c:
        assert c.get("/health").json()["w_version"] == 0

        # Day 0: free-form feed tags already match films by meaning (W = I).
        fid = c.post("/feeds", data={"tags": json.dumps({"dark comedy skits": 1.0, "late night memes": 0.3})}).json()["feed_id"]
        top = c.get(f"/feeds/{fid}/recs").json()["recs"][0]
        assert "dark comedy" in top["tags"] and top["because_of"][0] == "dark comedy skits"

        # Several gym-feed users each love some underdog films and pass on some recs.
        for u in range(8):
            h = as_(f"u{u}")
            fid = c.post("/feeds", data={"tags": json.dumps(gym_tags(rng))}, headers=h).json()["feed_id"]
            recs = c.get(f"/feeds/{fid}/recs", headers=h).json()["recs"]
            assert len(recs) == config.N_RECS
            for r in recs[:3]:
                assert c.post("/feedback", json={"rec_id": r["rec_id"], "label": "nah"}, headers=h).status_code == 200
            for idx in rng.sample(targets, 4):
                c.post("/feedback", json={"feed_id": fid, "movie_id": cat.movies[idx]["id"], "label": "love"}, headers=h)

        # A new gym user whose favourites are hidden = the held-out check.
        h = as_("new")
        fid = c.post("/feeds", data={"tags": json.dumps(gym_tags(rng))}, headers=h).json()["feed_id"]
        fav = c.post(f"/feeds/{fid}/favourites", headers=h,
                     json={"titles": [cat.movies[i]["title"] for i in targets[:5]], "holdout_frac": 1.0}).json()
        assert len(fav["matched"]) == 5 and all(m["split"] == "holdout" for m in fav["matched"])

        assert c.post("/admin/retrain").status_code == 403
        res = c.post("/admin/retrain", headers={"X-Admin-Token": "admin"}).json()
        assert res["accepted"] and res["recall_new"] > res["recall_old"], res
        assert c.get("/health").json()["w_version"] == res["version"]

        # The new user (zero feedback of their own) now gets underdog films, credited to their gym tags.
        recs = c.get(f"/feeds/{fid}/recs", headers=h).json()["recs"]
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


def test_screenshots_go_through_muse_and_ads_are_dropped(setup, monkeypatch):
    cat, store = setup

    async def fake_read(shots):
        return [(False, {"gym": 0.9, "brutalist architecture": 0.2}), (True, {"protein ad": 1.0})]

    monkeypatch.setattr(vision, "has_api_key", lambda: True)
    monkeypatch.setattr(vision, "read_screenshots", fake_read)
    with client(cat, store) as c:
        res = c.post("/feeds", files=[("files", ("a.png", b"\x89PNG", "image/png")),
                                      ("files", ("b.png", b"\x89PNG", "image/png"))]).json()
        assert res["dropped_as_noise"] == 1 and res["tags"] == {"gym": 0.9, "brutalist architecture": 0.2}


def test_muse_reply_parsing_is_tolerant():
    text = '```json\n{"is_ad_or_noise": false, "tags": [{"tag": " Gym  Rat ", "weight": 1.4}, {"tag": "", "weight": 0.5}]}\n```'
    assert vision.parse_reply(text) == (False, {"gym rat": 1.0})


def test_group_recs_per_member_and_average(setup, monkeypatch):
    cat, store = setup
    monkeypatch.setattr(config, "TAG_BOOST", 10.0)  # big enough that the 8 best picks must all be heist films
    heist = {cat.movies[i]["id"] for i in range(len(cat.movies)) if "heist" in cat.movies[i]["tags"]}
    with client(cat, store) as c:
        assert c.get("/me", headers=as_("a")).json()["feed_id"] is None
        fa = c.post("/feeds", data={"tags": json.dumps({"dark comedy": 1.0})}, headers=as_("a")).json()["feed_id"]
        c.post("/feeds", data={"tags": json.dumps({"romance": 1.0, "paris": 0.5})}, headers=as_("b"))
        assert c.get("/me", headers=as_("a")).json()["feed_id"] == fa

        # Others can't use a's feed; members without a feed can't be added.
        assert c.get(f"/feeds/{fa}/recs", headers=as_("b")).status_code == 403
        r = c.post("/groups", json={"user_ids": ["a", "nobody"]}, headers=as_("host"))
        assert r.status_code == 409 and r.json()["detail"]["needs_onboarding"] == ["nobody"]

        gid = c.post("/groups", json={"user_ids": ["a"]}, headers=as_("host")).json()["group_id"]
        assert c.post(f"/groups/{gid}/join", headers=as_("b")).json()["members"] == ["a", "b"]
        assert c.post(f"/groups/{gid}/recs", json={}, headers=as_("stranger")).status_code == 403

        plain = c.post(f"/groups/{gid}/recs", json={}, headers=as_("host")).json()
        assert set(plain["users"]) == {"a", "b"}
        assert all(len(lst) == config.N_RECS for lst in [*plain["users"].values(), plain["group"]])
        boosted = c.post(f"/groups/{gid}/recs", json={"boost": ["Heist "]}, headers=as_("host")).json()
        n_heist = lambda lst: sum(r["id"] in heist for r in lst)
        assert n_heist(plain["group"]) < 8
        assert n_heist(boosted["group"]) >= 8 and n_heist(boosted["users"]["a"]) >= 8

        shown = [r["id"] for r in plain["group"]]
        again = c.post(f"/groups/{gid}/recs", json={"exclude": shown}, headers=as_("b")).json()
        assert not set(shown) & {r["id"] for r in again["group"] + again["users"]["a"]}

        # A yes vote by movie id trains on the voter's latest feed.
        assert c.post("/feedback", json={"movie_id": shown[0], "label": "love"}, headers=as_("a")).status_code == 200
        assert cat.id_to_idx[shown[0]] in store.rated_movies(fa)
        assert c.post("/feedback", json={"movie_id": shown[0], "label": "love"}, headers=as_("nobody")).status_code == 409


def test_favourites_by_movie_id_one_at_a_time(setup):
    cat, store = setup
    with client(cat, store) as c:
        fid = c.post("/feeds", data={"tags": json.dumps({"gym": 1.0})}, headers=as_("a")).json()["feed_id"]
        splits = []
        for m in cat.movies[:40]:   # one call per film, like play.py's [f] key
            res = c.post(f"/feeds/{fid}/favourites", json={"movie_ids": [m["id"]]}, headers=as_("a")).json()
            assert [x["id"] for x in res["matched"]] == [m["id"]]
            splits.append(res["matched"][0]["split"])
        assert {"train", "holdout"} == set(splits)   # a shared seed would put every one on the same side
        assert c.post(f"/feeds/{fid}/favourites", json={"movie_ids": [-1]}, headers=as_("a")).json()["missing"] == [-1]
        assert store.count_events() == 40


def test_boost_matches_normalised_tags_exactly():
    movies = [{"tags": {"heist": 1}}, {"tags": {"heist movie": 1}}, {"tags": {}}]
    out = boost(np.zeros(3), movies, [" HEIST ", ""])
    assert out.tolist() == [config.TAG_BOOST, 0, 0]


def test_real_auth_rejects_missing_token_and_dev_auth_passes_name(setup, monkeypatch):
    cat, store = setup
    with TestClient(create_app(catalog=cat, store=store, start_trainer=False)) as c:
        assert c.get("/me").status_code == 401
        assert c.get("/me", headers=as_("forged")).status_code == 401
        monkeypatch.setattr(config, "DEV_AUTH", True)
        assert c.get("/me", headers=as_("alice")).json()["user"] == "alice"


def test_summarize_sums_up_the_feed_and_falls_back_to_the_average(monkeypatch):
    readings = [(False, {"curious": 0.8}), (False, {"curious": 0.4, "college football": 0.9}), (True, {"ad": 1.0})]
    monkeypatch.setattr(vision, "_client", lambda: None)

    async def fake_ask(client, content):
        assert "post 2: curious 0.40, college football 0.90" in content[0]["text"]
        return False, {"curious": 0.9}

    monkeypatch.setattr(vision, "_ask", fake_ask)
    assert asyncio.run(vision.summarize(readings)) == ({"curious": 0.9}, 1)

    async def broken_ask(client, content):
        raise RuntimeError("api down")

    monkeypatch.setattr(vision, "_ask", broken_ask)
    tags, dropped = asyncio.run(vision.summarize(readings))
    assert dropped == 1 and tags == pytest.approx({"curious": 0.6, "college football": 0.45})


def test_votes_pull_the_next_recs_before_any_retrain():
    cat = make_catalog()
    model = Translator(cat.w0).eval()
    x = cat.feed_vector({"dark comedy": 1.0})
    target = [i for i, m in enumerate(cat.movies) if m["title"].startswith("Underdog")]
    rank = lambda s, i: int((s > s[i]).sum())
    before = score_feed(model, x, cat.vecs)
    after = score_feed(model, x, cat.vecs, pos=set(target[:3]))
    # the unvoted underdog films climb because they share tags with the loved ones
    assert all(rank(after, i) < rank(before, i) for i in target[3:])


def test_popularity_weight_is_learned_and_old_checkpoints_still_load():
    cat = make_catalog()
    for i, m in enumerate(cat.movies):
        m["popularity"] = i
    cat = Catalog(cat.movies, cat.raw)
    prior = torch.from_numpy(cat.prior)
    rng = random.Random(0)
    hits = list(range(len(cat.movies) - 20, len(cat.movies)))   # every user loves the most-rated films, whatever their feed
    feeds = {f"f{u}": {"x": torch.from_numpy(cat.feed_vector({rng.choice(FILLER_TAGS): 1.0})),
                       "pos": set(rng.sample(hits, 3)), "neg": set()} for u in range(20)}
    examples = [(fid, j) for fid, f in feeds.items() for j in f["pos"]]
    m = Translator(cat.w0)
    opt = torch.optim.Adam(m.parameters(), lr=1e-2)
    for _ in range(50):
        opt.zero_grad()
        loss_fn(m, feeds, examples, torch.from_numpy(cat.vecs), prior=prior).backward()
        opt.step()
    assert m.pop.item() > config.POP_INIT + 0.1
    old = from_state(cat.w0, {"A": m.A.detach(), "B": m.B.detach()})   # pre-pop checkpoint
    assert old.pop.item() == pytest.approx(config.POP_INIT)
    assert from_state(cat.w0, state(m)).pop.item() == pytest.approx(m.pop.item())
