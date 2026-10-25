"""Real SQLite integration, Google auth doubles, no Supabase or model writes."""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["TANDEM_FAKE_ENCODER"] = "1"

import httpx
import numpy as np
import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient
from session_recommendations import final_ranking, mean_scores, verify_trailer
from sqlite_sessions import session_events
from tandem import config
from tandem.auth import current_user
from tandem.catalog import Catalog
from tandem.encoder import bag
from tandem.store import Store
from unified import create_app


class Clock:
    def __init__(self):
        self.now = 1800000000

    def __call__(self):
        return self.now


def auth(authorization: str = Header("")):
    token = authorization.removeprefix("Bearer ")
    if token not in {"tv", "a", "b", "c", "outsider"}:
        raise HTTPException(401, "Google sign-in required")
    return token


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("SWEEP_ENABLED", "false")
    movies = [
        {"id": i + 50, "tmdb_id": i + 900, "title": f"Movie {i}", "tags": {f"tag {i}": 1}}
        for i in range(15)
    ]
    cat = Catalog(movies, np.stack([bag(m["tags"]) for m in movies]))
    metadata = [
        {
            "source_id": i + 100,
            "provider": "tmdb",
            "provider_movie_id": str(i + 900),
            "title": f"Movie {i}",
            "trailer_provider": "youtube",
            "trailer_url": "https://www.youtube.com/watch?v=abcdefghijk",
        }
        for i in range(15)
    ]
    store = Store(tmp_path / "tandem.db")
    clock = Clock()

    def factory(store=store):
        app = create_app(cat, store, metadata, clock)
        app.dependency_overrides[current_user] = auth
        return app

    yield factory, store, clock
    store.db.close()


def post(c, path, user="tv", **kwargs):
    return c.post(path, headers={"Authorization": f"Bearer {user}"}, **kwargs)


def get(c, path, user="tv"):
    return c.get(path, headers={"Authorization": f"Bearer {user}"})


def lobby(c):
    made = post(c, "/sessions", json={"display_name": "TV"}).json()
    for user in ("a", "b", "c"):
        fid = post(c, "/feeds", user, data={"tags": '{"tag 1":1}'}).json()["feed_id"]
        assert (
            post(
                c,
                "/sessions/join",
                user,
                json={"display_name": user, "invite_token": made["invite_token"]},
            ).status_code
            == 200
        )
        assert (
            post(c, f"/sessions/{made['session_id']}/feed", user, json={"feed_id": fid}).status_code
            == 200
        )
    return made


async def playable(row):
    return True


def test_real_sqlite_tv_three_phones_concurrent_votes_and_controls(setup, monkeypatch):
    factory, store, clock = setup
    with TestClient(factory()) as c:
        monkeypatch.setattr(c.app.state.integration, "playable", playable)
        assert c.post("/sessions", json={"display_name": "TV"}).status_code == 401
        assert get(c, "/ready").json()["database"] == "sqlite"
        assert get(c, "/movies?limit=2").json()["total"] == 15
        assert len(get(c, "/movies?limit=2").json()["movies"]) == 2
        assert get(c, "/health").json()["movies"] == 15
        made = lobby(c)
        sid = made["session_id"]
        assert get(c, f"/sessions/{sid}", "outsider").status_code == 404
        assert post(c, f"/sessions/{sid}/queue", "a").status_code == 403
        assert post(c, f"/sessions/{sid}/queue").json()["added"] > 0
        state = get(c, f"/sessions/{sid}").json()
        assert all(50 <= m["movie_id"] < 65 for m in state["session_movies"])
        rid = post(c, f"/sessions/{sid}/control", json={"action": "start"}).json()["round_id"]
        assert (
            post(c, f"/sessions/{sid}/votes", json={"round_id": rid, "value": 1}).status_code == 403
        )
        assert post(c, f"/sessions/{sid}/control", "a", json={"action": "end"}).status_code == 403
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(
                pool.map(
                    lambda user: post(
                        c, f"/sessions/{sid}/votes", user, json={"round_id": rid, "value": 1}
                    ),
                    ("a", "b", "c"),
                )
            )
        assert all(r.status_code == 200 for r in responses)
        state = get(c, f"/sessions/{sid}").json()
        assert len(state["voting_rounds"]) == 2 and len(state["votes"]) == 3
        second = next(r["id"] for r in state["voting_rounds"] if r["closed_at"] is None)
        assert (
            post(c, f"/sessions/{sid}/votes", "a", json={"round_id": rid, "value": -1}).json()[
                "round_id"
            ]
            == second
        )
        assert len(get(c, f"/sessions/{sid}").json()["votes"]) == 3
        post(c, f"/sessions/{sid}/votes", "a", json={"round_id": second, "value": -1})
        clock.now += 44
        post(c, f"/sessions/{sid}/heartbeat", "a")
        clock.now += 2
        c.app.state.sessions.sweep()
        state = get(c, f"/sessions/{sid}").json()
        third = next(r["id"] for r in state["voting_rounds"] if r["closed_at"] is None)
        assert third != second
        assert (
            sum(
                p["excluded_at"] is not None
                for p in state["round_participants"]
                if p["round_id"] == second
            )
            == 2
        )
        assert c.app.state.sessions.sync_feedback(0) == 4
        assert c.app.state.sessions.sync_feedback(0) == 0
        assert store.count_events() == 4
        assert {"love", "nah"} == {e["label"] for e in store.events()}
        ranks = get(c, f"/sessions/{sid}/rankings").json()
        assert ranks[0]["unanimous"] and not ranks[1]["unanimous"]
        fourth = post(
            c, f"/sessions/{sid}/control", json={"action": "skip", "expected_round_id": third}
        ).json()["round_id"]
        assert fourth != third
        assert (
            post(
                c, f"/sessions/{sid}/control", json={"action": "skip", "expected_round_id": third}
            ).json()["round_id"]
            == fourth
        )
        assert post(c, f"/sessions/{sid}/control", json={"action": "end"}).status_code == 200
        assert get(c, f"/sessions/{sid}").json()["session"]["status"] == "ended"
        assert post(c, f"/sessions/{sid}/queue").status_code == 409
        assert post(c, "/admin/retrain").status_code == 403
        assert c.app.state.tandem["trainer"].thread is None
        assert store.db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failures_cannot_undo_votes_and_restart_preserves_data(setup, monkeypatch):
    factory, store, clock = setup
    with TestClient(factory()) as c:
        monkeypatch.setattr(c.app.state.integration, "playable", playable)
        made = lobby(c)
        sid = made["session_id"]
        post(c, f"/sessions/{sid}/queue")
        rid = post(c, f"/sessions/{sid}/control", json={"action": "start"}).json()["round_id"]
        post(c, f"/sessions/{sid}/votes", "a", json={"round_id": rid, "value": 1})

        async def unavailable(row):
            raise RuntimeError("provider offline")

        monkeypatch.setattr(c.app.state.integration, "playable", unavailable)
        assert post(c, f"/sessions/{sid}/queue").status_code == 503
        assert len(get(c, f"/sessions/{sid}").json()["votes"]) == 1
        # Failed feedback transaction rolls back its own work, never the accepted vote.
        with store.lock:
            store.db.execute(
                "CREATE TRIGGER fail_feedback BEFORE INSERT ON events BEGIN "
                "SELECT RAISE(ABORT,'test outage'); END"
            )
            store.db.commit()
        with pytest.raises(Exception, match="test outage"):
            c.app.state.sessions.sync_feedback(0)
        assert len(get(c, f"/sessions/{sid}").json()["votes"]) == 1
        with store.lock:
            store.db.execute("DROP TRIGGER fail_feedback")
            store.db.commit()
        assert c.app.state.sessions.sync_feedback(0) == 1
        before = {m["movie_id"] for m in get(c, f"/sessions/{sid}").json()["session_movies"]}
        monkeypatch.setattr(c.app.state.integration, "playable", playable)
        assert post(c, f"/sessions/{sid}/queue").json()["added"] > 0
        after = get(c, f"/sessions/{sid}").json()["session_movies"]
        assert len(after) == len({m["movie_id"] for m in after}) and before < {
            m["movie_id"] for m in after
        }
    dbpath = Path(store.db.execute("PRAGMA database_list").fetchone()[2])
    store.db.close()
    restored = Store(dbpath)
    try:
        with TestClient(factory(restored)) as c:
            state = get(c, f"/sessions/{sid}").json()
            assert len(state["votes"]) == 1 and state["session"]["host_user_id"] == "tv"
            assert restored.count_events() == 1
            assert c.app.state.sessions.sync_feedback(0) == 0
            assert len(restored._all("SELECT * FROM session_feeds")) == 3
    finally:
        restored.db.close()


def test_main_routes_latest_feed_auth_groups_and_boosts_survive(setup):
    factory, store, _ = setup
    with TestClient(factory()) as c:
        assert c.get("/me").status_code == 401
        fa = post(c, "/feeds", "a", data={"tags": '{"tag 1":1}'}).json()["feed_id"]
        fb = post(c, "/feeds", "b", data={"tags": '{"tag 2":1}'}).json()["feed_id"]
        assert get(c, "/me", "a").json()["feed_id"] == fa
        assert get(c, f"/feeds/{fa}/recs", "b").status_code == 404
        assert (
            post(c, f"/feeds/{fa}/favourites", "b", json={"titles": ["Movie 1"]}).status_code == 404
        )
        assert get(c, f"/feeds/{fa}/recs?boost=tag+1", "a").status_code == 200
        gid = post(c, "/groups", json={"user_ids": ["a"]}).json()["group_id"]
        assert post(c, f"/groups/{gid}/join", "b").status_code == 200
        assert post(c, f"/groups/{gid}/recs", "outsider", json={}).status_code == 403
        recs = post(c, f"/groups/{gid}/recs", json={"boost": ["tag 1"], "exclude": [50]}).json()
        assert set(recs["users"]) == {"a", "b"} and 50 not in {m["id"] for m in recs["group"]}
        assert post(c, "/feedback", "b", json={"movie_id": 50, "label": "love"}).status_code == 200
        assert store.events()[0]["feed_id"] == fb
        assert get(c, "/model", "a").status_code == 200
        assert get(c, "/movies/search?q=Movie", "a").status_code == 200
        assert get(c, "/session-catalog", "a").json()[0]["id"] in range(50, 65)


def test_invitation_rotation_and_vote_ownership(setup, monkeypatch):
    factory, store, _ = setup
    with TestClient(factory()) as c:
        monkeypatch.setattr(c.app.state.integration, "playable", playable)
        made = lobby(c)
        sid = made["session_id"]
        new = post(c, f"/sessions/{sid}/invitation").json()["invite_token"]
        assert (
            post(
                c,
                "/sessions/join",
                "outsider",
                json={"display_name": "Other", "invite_token": made["invite_token"]},
            ).status_code
            == 400
        )
        assert (
            post(
                c, "/sessions/join", "outsider", json={"display_name": "Other", "invite_token": new}
            ).status_code
            == 200
        )
        post(c, f"/sessions/{sid}/queue")
        rid = post(c, f"/sessions/{sid}/control", json={"action": "start"}).json()["round_id"]
        assert (
            post(
                c, f"/sessions/{sid}/votes", "a", json={"round_id": rid, "value": 1, "user_id": "b"}
            ).status_code
            == 200
        )
        votes = get(c, f"/sessions/{sid}").json()["votes"]
        assert votes[0]["user_id"] == "a"
        assert post(c, f"/sessions/{sid}/leave", "outsider").status_code == 200
        assert get(c, f"/sessions/{sid}", "outsider").status_code == 404


def test_authorized_event_stream_reconnects_and_rejects_outsiders(setup):
    factory, store, _ = setup

    class Connection:
        async def is_disconnected(self):
            return False

    async def check(sessions, sid):
        stream = session_events(sessions, sid, "tv", Connection(), interval=0)
        first = await stream.__anext__()
        assert "event: state" in first and sid in first
        sessions.heartbeat(sid, "a")
        changed = await stream.__anext__()
        assert changed != first
        await stream.aclose()
        reconnected = session_events(sessions, sid, "tv", Connection(), interval=0)
        assert await reconnected.__anext__() == changed
        await reconnected.aclose()

    with TestClient(factory()) as c:
        made = lobby(c)
        sid = made["session_id"]
        assert c.get(f"/sessions/{sid}/events").status_code == 401
        assert get(c, f"/sessions/{sid}/events", "outsider").status_code == 404
        asyncio.run(check(c.app.state.sessions, sid))


def test_trailer_validation_and_modular_ranking(monkeypatch):
    row = {
        "trailer_provider": "youtube",
        "trailer_url": "https://www.youtube.com/watch?v=abcdefghijk",
    }
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    async def checks():
        async with httpx.AsyncClient() as c:
            with pytest.raises(HTTPException):
                await verify_trailer(c, row)
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-only")

        def response(request):
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

        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as c:
            assert not await verify_trailer(c, row)

    asyncio.run(checks())
    assert np.allclose(mean_scores([[1, 3], [3, 1]]), [2, 2])
    rounds = [
        {"id": "r1", "movie_id": 50, "close_reason": "completed"},
        {"id": "r2", "movie_id": 51, "close_reason": "completed"},
    ]
    participants = [
        {"round_id": r, "user_id": u, "excluded_at": ("later" if u == "b" and r == "r2" else None)}
        for r in ("r1", "r2")
        for u in ("a", "b")
    ]
    votes = [
        {"round_id": r, "user_id": u, "value": (-1 if u == "b" and r == "r2" else 1)}
        for r in ("r1", "r2")
        for u in ("a", "b")
    ]
    assert final_ranking(rounds, participants, votes, {"50": -99, "51": 99})[0]["movie_id"] == 50


def test_railway_requires_volume_and_disallows_dev_auth(setup, monkeypatch):
    factory, _, _ = setup
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test")
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    with pytest.raises(RuntimeError, match="persistent volume"):
        with TestClient(factory()):
            pass
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")
    monkeypatch.setattr(config, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(config, "DEV_AUTH", True)
    with pytest.raises(RuntimeError, match="DEV_AUTH"):
        with TestClient(factory()):
            pass


def test_exported_contract():
    expected = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/openapi-unified.json").read_text()
    )
    assert create_app().openapi() == expected


def test_profiles_are_owned_and_shared_only_through_authorized_snapshot(setup):
    factory, store, _ = setup
    with TestClient(factory()) as c:
        made = lobby(c)
        sid = made["session_id"]
        assert (
            post(c, "/profiles/me", "a", json={"display_name": "Alice", "id": "b"}).json()["id"]
            == "a"
        )
        assert get(c, "/profiles/me", "a").json()["display_name"] == "Alice"
        assert get(c, "/profiles/me", "b").json()["display_name"] == "b"
        snapshot = get(c, f"/sessions/{sid}").json()
        assert any(p["id"] == "a" and p["display_name"] == "Alice" for p in snapshot["profiles"])
        assert get(c, f"/sessions/{sid}", "outsider").status_code == 404


def test_sse_delivery_and_reconnection_over_real_http(setup):
    import socket
    import threading
    import time

    import uvicorn

    factory, store, _ = setup
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            factory(),
            host="127.0.0.1",
            port=port,
            log_level="critical",
            timeout_graceful_shutdown=1,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    def receive(lines):
        for line in lines:
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise AssertionError("No SSE snapshot delivered")

    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as c:
            made = lobby(c)
            sid = made["session_id"]
            path = f"/sessions/{sid}/events"
            assert get(c, path, "outsider").status_code == 404
            assert c.get(path).status_code == 401
            with c.stream("GET", path, headers={"Authorization": "Bearer tv"}) as stream:
                assert stream.status_code == 200
                lines = stream.iter_lines()
                first = receive(lines)
                assert post(c, f"/sessions/{sid}/heartbeat", "a").status_code == 200
                changed = receive(lines)
                assert changed["session"]["revision"] > first["session"]["revision"]
            with c.stream("GET", path, headers={"Authorization": "Bearer tv"}) as stream:
                assert receive(stream.iter_lines()) == changed
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_migration_is_idempotent_and_preserves_existing_recommendation_data(tmp_path):
    from scripts.migrate_sqlite import migrate
    from sqlite_session_store import SessionStore

    cat = Catalog.load()
    path = tmp_path / "existing.db"
    store = Store(path)
    fid = store.add_feed("existing", {"heist": 1}, cat.feed_vector({"heist": 1}))
    store.add_event(fid, 7, "love", 0)
    SessionStore(store, cat, [])
    custom = {"provider": "tmdb", "provider_movie_id": "9479", "title": "Hand edited title"}
    with store.lock:
        store.db.execute(
            "INSERT INTO tandem_movie_metadata VALUES (?,?,?,?,?)",
            ("tmdb", "9479", 76, 551, json.dumps(custom)),
        )
        store.db.commit()
    vector = store.get_feed(fid)["x"].copy()
    store.db.close()
    source = Path(__file__).resolve().parents[1] / "catalog/session_movie_metadata.json"
    first = migrate(path, source)
    second = migrate(path, source)
    assert first["supplementary_metadata_rows"] == second["supplementary_metadata_rows"] == 200
    assert first["movie_catalog_rows"] == second["movie_catalog_rows"] == 5000
    assert first["recommendation_counts_before"] == first["recommendation_counts_after"]
    assert second["recommendation_counts_after"]["feeds"] == 1
    assert second["recommendation_counts_after"]["events"] == 1
    restored = Store(path)
    try:
        assert np.array_equal(restored.get_feed(fid)["x"], vector)
        row = restored._all(
            "SELECT details FROM tandem_movie_metadata WHERE provider_movie_id='9479'"
        )[0]
        assert json.loads(row["details"])["title"] == "Hand edited title"
    finally:
        restored.db.close()


def test_websocket_votes_reconnection_and_access_control(setup, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr("sqlite_sessions.current_user", auth)
    factory, _, _ = setup
    with TestClient(factory()) as c:
        monkeypatch.setattr(c.app.state.integration, "playable", playable)
        sid = lobby(c)["session_id"]
        path = f"/sessions/{sid}/ws"
        for token, code in [("invalid", 4401), ("outsider", 4403)]:
            with c.websocket_connect(path) as ws:
                ws.send_json({"type": "auth", "token": token})
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws.receive_json()
                assert closed.value.code == code
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(path, headers={"origin": "https://evil.example"}):
                pass
        with c.websocket_connect(path) as ws:
            ws.send_json([])
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        post(c, f"/sessions/{sid}/queue")
        rid = post(c, f"/sessions/{sid}/control", json={"action": "start"}).json()["round_id"]
        with c.websocket_connect(path) as ws:
            ws.send_json({"type": "auth", "token": "tv"})
            first = ws.receive_json()
            assert first["type"] == "state"
            with ThreadPoolExecutor(max_workers=3) as pool:
                responses = list(pool.map(lambda user: post(
                    c, f"/sessions/{sid}/votes", user, json={"round_id": rid, "value": 1}
                ), ("a", "b", "c")))
            assert all(r.status_code == 200 for r in responses)
            while True:
                changed = ws.receive_json()
                if len(changed["state"]["votes"]) == 3:
                    break
            assert changed["revision"] > first["revision"]
            assert len(changed["state"]["voting_rounds"]) == 2
        with c.websocket_connect(path) as ws:
            ws.send_json({"type": "auth", "token": "tv"})
            assert ws.receive_json() == changed
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
        with c.websocket_connect(path) as ws:
            ws.send_json({"type": "auth", "token": "a"})
            ws.receive_json()
            ws.send_json({"type": "heartbeat"})
            assert ws.receive_json()["revision"] > changed["revision"]
            post(c, f"/sessions/{sid}/leave", "a")
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4403
