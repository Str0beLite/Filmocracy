"""Training collection and opt-in trainer; isolated SQLite, synthetic images and no live APIs."""

import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
import test_unified as sessions
from fastapi.testclient import TestClient
from PIL import Image
from tandem import config, vision
from tandem.trainer import Trainer


@pytest.fixture
def training_setup(tmp_path, monkeypatch):
    yield from sessions.setup.__wrapped__(tmp_path, monkeypatch)


def shots(count=3, mime="image/png"):
    data = BytesIO()
    Image.new("RGB", (40, 40), "blue").save(data, "PNG")
    return [("files", (f"explore-{i}.png", data.getvalue(), mime)) for i in range(count)]


def muse(monkeypatch):
    async def read(images):
        assert 1 <= len(images) <= 3
        return []

    async def summarize(_):
        return {"tag 1": 1.0}, 0

    monkeypatch.setattr(vision, "has_api_key", lambda: True)
    monkeypatch.setattr(vision, "read_screenshots", read)
    monkeypatch.setattr(vision, "summarize", summarize)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_training_accepts_one_to_three_images_and_authenticated_owner(
    training_setup, monkeypatch, count
):
    factory, store, _ = training_setup
    muse(monkeypatch)
    with TestClient(factory()) as c:
        assert c.post("/training/feeds", files=shots()).status_code == 401
        for invalid_count in (0, 4):
            assert sessions.post(c, "/training/feeds", "a", files=shots(invalid_count)).status_code == 422
        assert sessions.post(c, "/training/feeds", "a", files=shots(mime="image/svg+xml")).status_code == 422
        assert sessions.post(c, "/training/feeds", "a", files=[("files", ("bad.png", b"not an image", "image/png"))] * 3).status_code == 422
        gif = BytesIO()
        Image.new("RGB", (40, 40), "blue").save(gif, "GIF")
        assert sessions.post(c, "/training/feeds", "a", files=[("files", ("bad.png", gif.getvalue(), "image/png"))] * 3).status_code == 422
        feed = sessions.post(c, "/training/feeds", "a", files=shots(count))
        assert feed.status_code == 200
        fid = feed.json()["feed_id"]
        assert store.get_feed(fid)["user"] == "a"
        path = f"/training/feeds/{fid}/next"
        assert c.post(path, json={}).status_code == 401
        assert sessions.post(c, path, "b", json={}).status_code == 403
        assert sessions.post(c, "/training/feeds/missing/next", "a", json={}).status_code == 404


def test_training_votes_playable_selection_no_repeats_and_restart(training_setup, monkeypatch):
    factory, store, _ = training_setup
    muse(monkeypatch)
    with TestClient(factory()) as c:
        fid = sessions.post(c, "/training/feeds", "a", files=shots()).json()["feed_id"]
        app = c.app
        calls = []

        async def playable(row):
            calls.append(row["id"])
            return row["id"] != 51

        app.state.integration.playable = playable
        path = f"/training/feeds/{fid}/next"
        first = sessions.post(c, path, "a", json={"boost": ["tag 1"]}).json()
        assert first["movie"]["id"] != 51
        assert first["movie"]["trailer_key"] == "abcdefghijk"
        assert first["movie"]["id"] in calls
        assert sessions.post(c, "/feedback", "b", json={"rec_id": first["rec_id"], "label": "love"}).status_code == 404
        assert sessions.post(c, "/feedback", "a", json={"rec_id": first["rec_id"], "label": "love"}).status_code == 200
        # Retrying an accepted vote leaves one label for this feed/movie.
        sessions.post(c, "/feedback", "a", json={"rec_id": first["rec_id"], "label": "love"})
        assert store.count_events() == 1
        assert store.events()[0]["feed_id"] == fid
        assert store.events()[0]["label"] == "love"

        async def unavailable(row):
            raise RuntimeError("provider unavailable")

        app.state.integration.playable = unavailable
        assert sessions.post(c, path, "a", json={}).status_code == 503
        assert store.count_events() == 1
        app.state.integration.playable = playable
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: sessions.post(c, path, "a", json={}).json(), range(2)))
        seen = {first["movie"]["id"], *(r["movie"]["id"] for r in results)}
        assert len(seen) == 3
        assert store._all("SELECT count(*) n FROM tandem_sessions")[0]["n"] == 0
    with TestClient(factory()) as c:
        c.app.state.integration.playable = playable
        for _ in range(20):
            response = sessions.post(c, path, "a", json={})
            if response.status_code == 409:
                break
            assert response.status_code == 200
            mid = response.json()["movie"]["id"]
            assert mid not in seen
            seen.add(mid)
        assert response.status_code == 409
        assert len(seen) == 14  # one deliberately unplayable catalog movie
        assert store.count_events() == 1


def test_opt_in_automatic_retraining_saves_only_temporary_checkpoints(
    training_setup, monkeypatch, tmp_path
):
    factory, store, _ = training_setup
    monkeypatch.setenv("TANDEM_TRAINING_ENABLED", "1")
    monkeypatch.setattr(config, "RETRAIN_EVERY", 1)
    monkeypatch.setattr(config, "SEED_W", tmp_path / "no-seed.pt")
    monkeypatch.setattr(config, "CKPT_DIR", tmp_path / "checkpoints")
    original = Trainer.retrain
    monkeypatch.setattr(Trainer, "retrain", lambda self: original(self, steps=2))
    with TestClient(factory()) as c:
        assert c.get("/ready").json()["training_enabled"] is True
        trainer = c.app.state.tandem["trainer"]
        assert trainer.thread.is_alive()
        fid = sessions.post(c, "/feeds", "a", data={"tags": '{"tag 1":1}'}).json()["feed_id"]
        assert sessions.post(c, "/feedback", "a", json={"feed_id": fid, "movie_id": 51, "label": "love"}).status_code == 200
        deadline = time.monotonic() + 15
        while not store.models() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert store.models(), "The existing trainer did not wake after feedback"
        assert (tmp_path / "checkpoints/w_v1.pt").is_file()
        assert store.models()[0]["path"].startswith(str(tmp_path))
        assert trainer.current()[0] == 1
        # Public callers still cannot force a retrain via the admin endpoint.
        assert sessions.post(c, "/admin/retrain", "a").status_code == 403
    assert not trainer.thread.is_alive()


def test_training_defaults_off(training_setup, monkeypatch):
    monkeypatch.delenv("TANDEM_TRAINING_ENABLED", raising=False)
    factory, _, _ = training_setup
    with TestClient(factory()) as c:
        assert c.get("/ready").json()["training_enabled"] is False
        assert c.app.state.tandem["trainer"].thread is None


@pytest.mark.parametrize("label,positive", [
    ("love", True), ("nah", False), ("seen_loved", True), ("seen_disliked", False)
])
def test_four_training_votes_keep_seen_label_and_training_direction(training_setup, label, positive):
    factory, store, _ = training_setup
    with TestClient(factory()) as c:
        fid = sessions.post(c, "/feeds", "a", data={"tags": '{"tag 1":1}'}).json()["feed_id"]
        rec = sessions.get(c, f"/feeds/{fid}/recs", "a").json()["recs"][0]
        response = sessions.post(c, "/feedback", "a", json={"rec_id": rec["rec_id"], "label": label})
        assert response.status_code == 200
        assert store.events()[0]["label"] == label
        idx = c.app.state.tandem["catalog"].id_to_idx[rec["id"]]
        loved, passed = store.votes(fid)
        assert idx in (loved if positive else passed)
        assert idx not in (passed if positive else loved)
        feeds, _, _, _ = c.app.state.tandem["trainer"].build_dataset()
        assert idx in feeds[fid]["pos" if positive else "neg"]
        assert idx in store.rated_movies(fid)


def test_session_vote_sync_wakes_the_same_trainer(training_setup, monkeypatch, tmp_path):
    factory, store, _ = training_setup
    monkeypatch.setenv("TANDEM_TRAINING_ENABLED", "1")
    monkeypatch.setattr(config, "RETRAIN_EVERY", 1)
    monkeypatch.setattr(config, "SEED_W", tmp_path / "no-seed.pt")
    monkeypatch.setattr(config, "CKPT_DIR", tmp_path / "checkpoints")
    original = Trainer.retrain
    monkeypatch.setattr(Trainer, "retrain", lambda self: original(self, steps=2))
    with TestClient(factory()) as c:
        c.app.state.integration.playable = sessions.playable
        sid = sessions.lobby(c)["session_id"]
        assert sessions.post(c, f"/sessions/{sid}/queue").status_code == 200
        rid = sessions.post(c, f"/sessions/{sid}/control", json={"action": "start"}).json()["round_id"]
        for user in ("a", "b", "c"):
            assert sessions.post(c, f"/sessions/{sid}/votes", user, json={"round_id": rid, "value": 1}).status_code == 200
        deadline = time.monotonic() + 15
        while not store.models() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert store.models(), "The maintenance loop did not notify the trainer after session feedback"
        assert store.count_events() == 3
        assert len(sessions.get(c, f"/sessions/{sid}").json()["votes"]) == 3
        assert store.models()[0]["path"].startswith(str(tmp_path))
        assert sessions.post(c, f"/sessions/{sid}/control", json={"action": "end"}).status_code == 200
