"""Real Auth -> FastAPI HTTP -> Supabase/RLS. Opt-in development writes only."""

import asyncio
import os
import unittest
from unittest.mock import patch

import httpx
from live_support import LiveFixtures, test_settings

import app as backend


class LiveBackendCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url, key, secret = test_settings()
        self.fixtures = LiveFixtures(url, key, secret)
        self.addAsyncCleanup(self.fixtures.cleanup)
        await self.fixtures.create_users()
        await self.fixtures.seed_movies()
        self.env = patch.dict(
            os.environ,
            {
                "SUPABASE_URL": url,
                "SUPABASE_PUBLISHABLE_KEY": key,
                "SUPABASE_SECRET_KEY": secret,
                "SWEEP_ENABLED": "false",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.lifespan = backend.lifespan(backend.app)
        await self.lifespan.__aenter__()
        self.addAsyncCleanup(self.lifespan.__aexit__, None, None, None)
        self.api = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=backend.app), base_url="http://test"
        )
        self.addAsyncCleanup(self.api.aclose)

    async def call(self, role, method, path, body=None, status=200):
        for attempt in range(3):
            response = await self.api.request(
                method,
                path,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.fixtures.users[role]['access_token']}",
                },
            )
            if method == "GET" and response.status_code == 503 and attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            break
        self.assertEqual(response.status_code, status, f"{method} {path} status")
        return response.json()

    async def state(self):
        return await self.call("tv", "GET", f"/sessions/{self.session_id}")

    @staticmethod
    def current(state):
        return next(r["id"] for r in state["voting_rounds"] if r["closed_at"] is None)


class LiveBackendTests(LiveBackendCase):
    async def test_tv_three_phones_lifecycle_and_security(self):
        created = await self.call("tv", "POST", "/sessions", {"display_name": "Test TV"})
        self.session_id = created["session_id"]
        path = f"/sessions/{self.session_id}"
        for role in ("alice", "bob", "carol"):
            joined = await self.call(
                role,
                "POST",
                "/sessions/join",
                {
                    "display_name": role,
                    "invite_token": created["invite_token"],
                },
            )
            self.assertEqual(joined["session_id"], self.session_id)
        self.assertEqual(len((await self.state())["session_members"]), 4)

        # Queue the run's own fixture IDs without changing/calling the recommender.
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
        self.assertEqual(len((await self.state())["round_participants"]), 3)
        for role in ("alice", "bob"):
            await self.call(role, "POST", path + "/votes", {"round_id": first, "value": 1})
        self.assertEqual(self.current(await self.state()), first)
        # Repeated final vote requests must close exactly once.
        await asyncio.gather(
            *[
                self.call("carol", "POST", path + "/votes", {"round_id": first, "value": -1})
                for _ in range(2)
            ]
        )
        state = await self.state()
        self.assertEqual(len(state["voting_rounds"]), 2)
        self.assertEqual(len(state["votes"]), 3)
        second = self.current(state)
        for role in ("alice", "bob"):
            await self.call(role, "POST", path + "/votes", {"round_id": second, "value": 1})

        # Stop Carol's heartbeat. Keep the other phones connected while waiting
        # for the real 45-second database lease; do not rewrite timestamps via admin.
        for _ in range(5):
            await asyncio.sleep(10)
            for role in ("alice", "bob"):
                await self.call(role, "POST", path + "/heartbeat")
        state = await self.state()
        third = self.current(state)
        self.assertNotEqual(third, second)
        self.assertEqual(len(state["voting_rounds"]), 3)
        carol_id = self.fixtures.users["carol"]["id"]
        self.assertTrue(
            next(
                p
                for p in state["round_participants"]
                if p["round_id"] == second and p["user_id"] == carol_id
            )["excluded_at"]
        )
        await self.call("carol", "POST", path + "/heartbeat")
        await self.call(
            "carol", "POST", path + "/votes", {"round_id": third, "value": 1}, status=403
        )

        # Missing, forged, outsider, and non-host authority checks hit real Auth/RLS.
        self.assertEqual((await self.api.get(path)).status_code, 401)
        self.assertEqual(
            (
                await self.api.get(
                    path,
                    headers={
                        "Authorization": "Bearer forged-token",
                    },
                )
            ).status_code,
            401,
        )
        await self.call("outsider", "GET", path, status=404)
        await self.call(
            "outsider", "POST", path + "/votes", {"round_id": third, "value": 1}, status=403
        )
        for action in ("skip", "end"):
            await self.call(
                "alice",
                "POST",
                path + "/control",
                {
                    "action": action,
                    "expected_round_id": third,
                },
                status=403,
            )
        direct = await self.fixtures.client.patch(
            "/rest/v1/votes",
            headers={
                "apikey": self.fixtures.key,
                "Authorization": f"Bearer {self.fixtures.users['alice']['access_token']}",
            },
            params={"round_id": f"eq.{first}", "user_id": f"eq.{carol_id}"},
            json={"value": 1},
        )
        self.assertIn(direct.status_code, (401, 403))
        for _ in range(2):
            await self.call(
                "tv",
                "POST",
                path + "/control",
                {
                    "action": "skip",
                    "expected_round_id": third,
                },
            )
        state = await self.state()
        self.assertEqual(len(state["voting_rounds"]), 4)
        self.assertEqual(
            next(r for r in state["voting_rounds"] if r["id"] == third)["close_reason"], "skipped"
        )
        await self.call("bob", "POST", path + "/leave")
        await self.call("tv", "POST", path + "/control", {"action": "end"})
        state = await self.state()
        self.assertEqual(state["session"]["status"], "ended")
        self.assertFalse(any(r["closed_at"] is None for r in state["voting_rounds"]))
        await self.call(
            "outsider",
            "POST",
            "/sessions/join",
            {
                "display_name": "outsider",
                "invite_token": created["invite_token"],
            },
            status=400,
        )
