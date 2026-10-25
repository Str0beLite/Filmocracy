"""Actual Supabase WebSocket delivery, RLS isolation, and reconnect snapshot recovery."""

import asyncio
import json
from urllib.parse import urlencode

from test_live_backend import LiveBackendCase
from websockets.asyncio.client import connect

TABLES = (
    "group_sessions",
    "session_members",
    "session_movies",
    "voting_rounds",
    "round_participants",
    "votes",
)


class Subscriber:
    """Test-only client for the documented Realtime JSON 1.0 protocol; no SDK mocks."""

    def __init__(self, fixtures, token, session_id):
        self.url = (
            fixtures.url.replace("https://", "wss://")
            + "/realtime/v1/websocket?"
            + urlencode(
                {
                    "apikey": fixtures.key,
                    "vsn": "1.0.0",
                }
            )
        )
        self.token, self.session_id = token, session_id
        self.socket = None

    async def close(self):
        if self.socket:
            await self.socket.close()
            self.socket = None

    async def open(self):
        self.socket = await connect(self.url, open_timeout=15)
        await self.socket.send(
            json.dumps(
                {
                    "topic": "realtime:integration",
                    "event": "phx_join",
                    "ref": "1",
                    "join_ref": "1",
                    "payload": {
                        "access_token": self.token,
                        "config": {
                            "broadcast": {"ack": False, "self": False},
                            "presence": {"enabled": False},
                            "private": False,
                            "postgres_changes": [
                                {
                                    "event": "*",
                                    "schema": "public",
                                    "table": table,
                                    "filter": (
                                        f"{'id' if table == 'group_sessions' else 'session_id'}"
                                        f"=eq.{self.session_id}"
                                    ),
                                }
                                for table in TABLES
                            ],
                        },
                    },
                }
            )
        )

        async def ready():
            joined = False
            streaming = False
            while not (joined and streaming):
                frame = await self.frame()
                payload = frame.get("payload", {})
                if frame["event"] == "phx_reply":
                    if payload.get("status") != "ok":
                        raise AssertionError("Realtime channel rejected the subscription")
                    registrations = payload.get("response", {}).get("postgres_changes", [])
                    if len(registrations) != len(TABLES):
                        raise AssertionError("Realtime did not register all six tables")
                    joined = True
                if frame["event"] == "system" and payload.get("extension") == "postgres_changes":
                    streaming = payload.get("status") == "ok"

        try:
            await asyncio.wait_for(ready(), 20)
        except BaseException:
            await self.close()
            raise

    async def frame(self):
        frame = json.loads(await self.socket.recv())
        payload = frame.get("payload", {})
        if frame["event"] in ("phx_error", "phx_close") or (
            frame["event"] == "system" and payload.get("status") == "error"
        ):
            raise AssertionError("Realtime subscription failed; no payload/credentials logged")
        return frame

    async def change(self, timeout=10):
        async def receive():
            while True:
                frame = await self.frame()
                if frame["event"] == "postgres_changes":
                    return frame["payload"]["data"]

        return await asyncio.wait_for(receive(), timeout)


class LiveRealtimeTests(LiveBackendCase):
    async def test_delivery_isolation_reconnect_and_snapshot(self):
        created = await self.call("tv", "POST", "/sessions", {"display_name": "Realtime TV"})
        self.session_id = created["session_id"]
        path = f"/sessions/{self.session_id}"
        authorized = Subscriber(
            self.fixtures, self.fixtures.users["tv"]["access_token"], self.session_id
        )
        outsider = Subscriber(
            self.fixtures, self.fixtures.users["outsider"]["access_token"], self.session_id
        )
        self.addAsyncCleanup(authorized.close)
        self.addAsyncCleanup(outsider.close)
        await authorized.open()
        await outsider.open()
        for role in ("alice", "bob", "carol"):
            await self.call(
                role,
                "POST",
                "/sessions/join",
                {
                    "display_name": role,
                    "invite_token": created["invite_token"],
                },
            )
        await self.fixtures.request(
            "POST",
            "/rest/v1/rpc/enqueue_movies",
            token=self.fixtures.users["tv"]["access_token"],
            body={
                "p_session": self.session_id,
                "p_movies": self.fixtures.movie_ids,
            },
        )
        first = (await self.call("tv", "POST", path + "/control", {"action": "start"}))["round_id"]
        await self.call("alice", "POST", path + "/votes", {"round_id": first, "value": 1})
        received = set()

        async def all_tables():
            while received != set(TABLES):
                event = await authorized.change()
                record = event["record"]
                self.assertEqual(record.get("session_id", record.get("id")), self.session_id)
                received.add(event["table"])

        await asyncio.wait_for(all_tables(), 20)
        # An outsider's Postgres Changes channel join may succeed, but RLS must
        # deliver no private row events. A positive authorized control ran above.
        with self.assertRaises(asyncio.TimeoutError):
            await outsider.change(timeout=3)
        await self.call("outsider", "GET", path, status=404)
        outsider_rows = await self.fixtures.request(
            "GET",
            "/rest/v1/votes",
            token=self.fixtures.users["outsider"]["access_token"],
            params={
                "session_id": f"eq.{self.session_id}",
                "select": "*",
            },
        )
        self.assertEqual(outsider_rows, [])
        await authorized.close()
        await self.call("bob", "POST", path + "/votes", {"round_id": first, "value": 1})
        # Refresh the same TV identity, then rejoin before fetching the missed state.
        old_id = self.fixtures.users["tv"]["id"]
        refreshed = await self.fixtures.request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "refresh_token"},
            body={
                "refresh_token": self.fixtures.users["tv"]["refresh_token"],
            },
        )
        self.assertEqual(refreshed["user"]["id"], old_id)
        self.fixtures.users["tv"].update(refreshed)
        authorized.token = refreshed["access_token"]
        await authorized.open()
        state = await self.state()
        self.assertEqual(state["session"]["host_user_id"], old_id)
        self.assertEqual(self.current(state), first)
        self.assertEqual(len(state["votes"]), 2)  # Includes the vote missed while offline.
        await self.call("alice", "POST", path + "/votes", {"round_id": first, "value": -1})

        async def changed_vote():
            while True:
                event = await authorized.change()
                if event["table"] == "votes":
                    self.assertEqual(event["record"]["value"], -1)
                    return

        await asyncio.wait_for(changed_vote(), 10)
