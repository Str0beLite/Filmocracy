"""Unified routes use an isolated stateful Supabase double; no live writes."""

import asyncio
import json
import os
from uuid import uuid4

os.environ["TANDEM_FAKE_ENCODER"] = "1"

import httpx
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from session_recommendations import final_ranking, mean_scores, movie_mapping
from tandem.catalog import Catalog
from tandem.encoder import bag
from tandem.store import Store
from unified import create_app


class Database:
    def __init__(self):
        self.sid = str(uuid4())
        self.members = []
        self.queue = []
        self.rounds = []
        self.participants = []
        self.votes = []
        self.session = {"id": self.sid, "host_user_id": "tv", "status": "lobby"}
        self.client = httpx.AsyncClient()
        self.movies = [
            {
                "id": i + 100,
                "provider": "tmdb",
                "provider_movie_id": str(i + 900),
                "trailer_provider": "YouTube",
                "trailer_url": "https://www.youtube.com/watch?v=abcdefghijk",
            }
            for i in range(12)
        ]

    async def request(self, method, path, token=None, params=None, **kwargs):
        if path == "/auth/v1/user":
            if token not in ("tv", "a", "b", "c", "outsider"):
                raise HTTPException(401)
            return {"id": token}
        table = path.rsplit("/", 1)[-1]
        if table != "movies" and token and token != "tv" and token not in self.members:
            return []
        return {
            "group_sessions": [self.session],
            "movies": self.movies,
            "session_members": [
                {"user_id": u, "is_voter": True, "left_at": None} for u in self.members
            ],
            "session_movies": self.queue,
            "voting_rounds": self.rounds,
            "round_participants": self.participants,
            "votes": self.votes,
        }[table]

    def advance(self):
        shown = {r["movie_id"] for r in self.rounds}
        remaining = [m for m in self.queue if m["movie_id"] not in shown]
        if not remaining:
            return None
        rid = str(uuid4())
        self.rounds.append({"id": rid, "movie_id": remaining[0]["movie_id"], "close_reason": None})
        self.participants.extend(
            {"round_id": rid, "user_id": u, "excluded_at": None} for u in self.members
        )
        return rid

    async def rpc(self, name, body, token=None, **kwargs):
        if name == "create_session":
            return {"session_id": self.sid, "invite_token": "x" * 64}
        if name == "join_session":
            self.members.append(token)
            return self.sid
        if name == "enqueue_movies":
            for mid in body["p_movies"]:
                if mid not in {m["movie_id"] for m in self.queue}:
                    self.queue.append({"movie_id": mid})
            return len(body["p_movies"])
        if name == "control_session":
            if body["p_action"] == "end":
                self.session["status"] = "ended"
                return None
            return self.advance()
        if name == "cast_vote":
            self.votes.append(
                {"round_id": body["p_round"], "user_id": token, "value": body["p_value"]}
            )
            if sum(v["round_id"] == body["p_round"] for v in self.votes) == len(self.members):
                next(r for r in self.rounds if r["id"] == body["p_round"])["close_reason"] = (
                    "completed"
                )
                return self.advance()
            return body["p_round"]


@pytest.fixture
def components(tmp_path, monkeypatch):
    monkeypatch.setenv("SWEEP_ENABLED", "false")
    movies = [
        {"id": i + 50, "tmdb_id": i + 900, "title": f"Movie {i}", "tags": {f"tag {i}": 1}}
        for i in range(12)
    ]
    cat = Catalog(movies, np.stack([bag(m["tags"]) for m in movies]))
    return cat, Store(tmp_path / "tandem.db"), Database()


def test_unified_round_trip_and_restart(components, monkeypatch):
    cat, store, db = components

    async def playable(row):
        return True

    with TestClient(create_app(cat, store, db)) as c:
        monkeypatch.setattr(c.app.state.integration, "playable", playable)

        def post(path, user="tv", **kwargs):
            return c.post(path, headers={"Authorization": f"Bearer {user}"}, **kwargs)

        assert c.post("/feeds", data={"tags": '{"tag 1":1}'}).status_code == 401
        assert post("/sessions", json={"display_name": "TV"}).status_code == 200
        sid = db.sid
        for user in ("a", "b", "c"):
            assert (
                post(
                    "/sessions/join", user, json={"display_name": user, "invite_token": "x" * 64}
                ).status_code
                == 200
            )
            fid = post("/feeds", user, data={"tags": '{"tag 1":1}', "user": "spoof"}).json()[
                "feed_id"
            ]
            assert store.get_feed(fid)["user"] == user
            recs = c.get(f"/feeds/{fid}/recs", headers={"Authorization": f"Bearer {user}"}).json()
            rec_id = recs["recs"][0]["rec_id"]
            assert (
                post("/feedback", "outsider", json={"rec_id": rec_id, "label": "nah"}).status_code
                == 404
            )
            assert (
                post(
                    f"/feeds/{fid}/favourites", "outsider", json={"titles": ["Movie 1"]}
                ).status_code
                == 404
            )
            assert (
                c.get(
                    f"/feeds/{fid}/recs", headers={"Authorization": "Bearer outsider"}
                ).status_code
                == 404
            )
            assert post(f"/sessions/{sid}/feed", user, json={"feed_id": fid}).status_code == 200
        assert post(f"/sessions/{sid}/queue", "a").status_code == 403
        assert post(f"/sessions/{sid}/queue").json()["added"] > 0
        rid = post(f"/sessions/{sid}/control", json={"action": "start"}).json()["round_id"]
        for user in ("a", "b", "c"):
            response = post(f"/sessions/{sid}/votes", user, json={"round_id": rid, "value": 1})
            assert response.status_code == 200
        assert response.json()["round_id"] != rid

        # Scoring outage does not affect accepted voting or host termination.
        async def unavailable(row):
            raise RuntimeError("offline")

        monkeypatch.setattr(c.app.state.integration, "playable", unavailable)
        assert post(f"/sessions/{sid}/queue").status_code == 503
        before = {m["movie_id"] for m in db.queue}
        monkeypatch.setattr(c.app.state.integration, "playable", playable)
        post(f"/sessions/{sid}/queue")
        assert len(db.queue) == len({m["movie_id"] for m in db.queue})
        assert before <= {m["movie_id"] for m in db.queue}
        assert len(db.queue) > len(before)
        original_add_event = store.add_event

        def offline(*args, **kwargs):
            raise RuntimeError("SQLite temporarily unavailable")

        monkeypatch.setattr(store, "add_event", offline)
        with pytest.raises(RuntimeError):
            asyncio.run(c.app.state.integration.reconcile())
        assert len(db.votes) == 3
        monkeypatch.setattr(store, "add_event", original_add_event)
        asyncio.run(c.app.state.integration.reconcile())
        asyncio.run(c.app.state.integration.reconcile())
        assert store.count_events() == 3
        assert {e["label"] for e in store.events()} == {"love"}
        ranks = c.get(f"/sessions/{sid}/rankings", headers={"Authorization": "Bearer tv"}).json()
        assert ranks[0]["unanimous"]
        assert post("/admin/retrain").status_code == 403
        assert c.get("/model", headers={"Authorization": "Bearer a"}).status_code == 200
        assert (
            c.get("/movies/search?q=Movie", headers={"Authorization": "Bearer a"}).status_code
            == 200
        )
        assert post(f"/sessions/{sid}/control", json={"action": "end"}).status_code == 200
        paths = c.get("/openapi.json").json()["paths"]
        assert "/sessions" in paths and "/feeds" in paths
    path = store.db.execute("PRAGMA database_list").fetchone()[2]
    store.db.close()
    restored = Store(__import__("pathlib").Path(path))
    with TestClient(create_app(cat, restored, db)) as c:
        assert len(restored._all("SELECT * FROM session_feeds")) == 3
        assert restored.count_events() == 3
        assert len(restored._all("SELECT * FROM vote_sync")) == 3
    restored.db.close()
    asyncio.run(db.client.aclose())


def test_mapping_aggregation_and_consensus():
    cat = type("Catalog", (), {"movies": [{"id": 12, "tmdb_id": 1000}]})()
    assert movie_mapping(cat, [{"id": 999, "provider": "tmdb", "provider_movie_id": "1000"}]) == {
        999: 0
    }
    assert np.allclose(mean_scores([[1, 3], [3, 1]]), [2, 2])
    ambiguous = type("Catalog", (), {"movies": cat.movies * 2})()
    assert (
        movie_mapping(ambiguous, [{"id": 999, "provider": "tmdb", "provider_movie_id": "1000"}])
        == {}
    )
    rounds = [
        {"id": "r1", "movie_id": 1, "close_reason": "completed"},
        {"id": "r2", "movie_id": 2, "close_reason": "completed"},
    ]
    participants = [{"round_id": r, "user_id": u} for r in ("r1", "r2") for u in ("a", "b")]
    votes = [
        {"round_id": r, "user_id": u, "value": (-1 if r == "r2" and u == "b" else 1)}
        for r in ("r1", "r2")
        for u in ("a", "b")
    ]
    assert final_ranking(rounds, participants, votes, {"1": -100, "2": 100})[0]["movie_id"] == 1
    # Disconnecting after a dislike must never turn a mixed round unanimous.
    for participant in participants:
        if participant["round_id"] == "r2" and participant["user_id"] == "b":
            participant["excluded_at"] = "2026-10-24T00:00:00Z"
    ranked = final_ranking(rounds, participants, votes, {"1": -100, "2": 100})
    assert ranked[1]["dislikes"] == 1 and not ranked[1]["unanimous"]


def test_playback_validation_fails_closed(components, monkeypatch):
    cat, store, db = components
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with TestClient(create_app(cat, store, db)) as c:
        integration = c.app.state.integration
        original = db.client
        with pytest.raises(HTTPException) as error:
            asyncio.run(integration.playable(db.movies[0]))
        assert error.value.status_code == 503
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-only")

        async def available(request):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "status": {"embeddable": True, "privacyStatus": "public"},
                            "contentDetails": {},
                        }
                    ]
                },
            )

        db.client = httpx.AsyncClient(transport=httpx.MockTransport(available))
        assert asyncio.run(integration.playable(db.movies[0])) is True
        integration.trailers.clear()

        async def blocked(request):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "status": {"embeddable": True, "privacyStatus": "public"},
                            "contentDetails": {"regionRestriction": {"blocked": ["US"]}},
                        }
                    ]
                },
            )

        asyncio.run(db.client.aclose())
        db.client = httpx.AsyncClient(transport=httpx.MockTransport(blocked))
        assert asyncio.run(integration.playable(db.movies[0])) is False
        asyncio.run(db.client.aclose())
        db.client = original
    store.db.close()
    asyncio.run(db.client.aclose())


def test_railway_requires_persistent_volume(components, monkeypatch):
    cat, store, db = components
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test")
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    with pytest.raises(RuntimeError, match="persistent volume"):
        with TestClient(create_app(cat, store, db)):
            pass
    store.db.close()
    asyncio.run(db.client.aclose())


def test_exported_unified_contract():
    from pathlib import Path

    expected = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/openapi-unified.json").read_text()
    )
    assert create_app().openapi() == expected
