import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as backend
from recommendations import MockRecommendationProvider, RecommendationContext


class RecommendationTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_preserves_order_excludes_history_and_limits(self):
        context = RecommendationContext("session", [9, 2, 9, 5, 7], frozenset({2}))
        result = await MockRecommendationProvider().movie_ids(context, 2)
        self.assertEqual(result, [9, 5])


class SupabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_bad_jwt_is_401_while_rls_denials_remain_403(self):
        async def handler(request):
            body = (
                {"code": 403, "error_code": "bad_jwt"}
                if request.url.path == "/auth/v1/user"
                else {"code": "42501"}
            )
            return httpx.Response(403, json=body)

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.test",
                "SUPABASE_PUBLISHABLE_KEY": "public",
                "SUPABASE_SECRET_KEY": "secret",
            },
        ):
            db = backend.Supabase()
        await db.client.aclose()
        db.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            for path, expected in (("/auth/v1/user", 401), ("/rest/v1/rpc/cast_vote", 403)):
                with self.assertRaises(HTTPException) as error:
                    await db.request("GET", path, token="invalid")
                self.assertEqual(error.exception.status_code, expected)
        finally:
            await db.client.aclose()

    async def test_concurrent_callers_keep_distinct_auth_headers(self):
        seen = []

        async def handler(request):
            seen.append(request.headers["Authorization"])
            return httpx.Response(200, json=[])

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.test",
                "SUPABASE_PUBLISHABLE_KEY": "public",
                "SUPABASE_SECRET_KEY": "secret",
            },
        ):
            db = backend.Supabase()
        await db.client.aclose()
        db.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await asyncio.gather(
                db.rpc("heartbeat", {}, token="alice"), db.rpc("heartbeat", {}, token="bob")
            )
        finally:
            await db.client.aclose()
        self.assertEqual(set(seen), {"Bearer alice", "Bearer bob"})

    async def test_upstream_errors_do_not_expose_tokens_or_database_details(self):
        async def handler(request):
            return httpx.Response(403, json={"code": "42501", "message": "private data"})

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.test",
                "SUPABASE_PUBLISHABLE_KEY": "public",
                "SUPABASE_SECRET_KEY": "secret",
            },
        ):
            db = backend.Supabase()
        await db.client.aclose()
        db.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with self.assertRaises(HTTPException) as error:
                await db.rpc("cast_vote", {}, token="private-token")
            self.assertEqual(error.exception.status_code, 403)
            self.assertEqual(error.exception.detail, "Request rejected by Supabase")
        finally:
            await db.client.aclose()


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = AsyncMock()
        backend.app.state.db = self.db
        backend.app.dependency_overrides[backend.user_token] = lambda: "alice-token"
        self.client = TestClient(backend.app)

    def tearDown(self):
        backend.app.dependency_overrides.clear()
        self.client.close()

    def test_skip_requires_round_identifier(self):
        response = self.client.post(f"/sessions/{uuid4()}/control", json={"action": "skip"})
        self.assertEqual(response.status_code, 422)
        self.db.rpc.assert_not_called()

    def test_vote_uses_caller_token_and_round(self):
        session_id, round_id = uuid4(), uuid4()
        self.db.rpc.return_value = str(round_id)
        response = self.client.post(
            f"/sessions/{session_id}/votes",
            json={
                "round_id": str(round_id),
                "value": 1,
                "user_id": "someone-else",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.db.rpc.assert_awaited_once_with(
            "cast_vote",
            {
                "p_session": str(session_id),
                "p_round": str(round_id),
                "p_value": 1,
            },
            token="alice-token",
        )

    def test_snapshot_hides_unrelated_session(self):
        self.db.request.return_value = []
        response = self.client.get(f"/sessions/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_invalid_vote_rejected(self):
        response = self.client.post(
            f"/sessions/{uuid4()}/votes",
            json={
                "round_id": str(uuid4()),
                "value": 0,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.db.rpc.assert_not_called()


class LifespanTests(unittest.TestCase):
    def test_sweeper_can_be_disabled_for_fixture_isolated_tests(self):
        db = AsyncMock()
        with patch.dict("os.environ", {"SWEEP_ENABLED": "false"}):
            with patch.object(backend, "Supabase", return_value=db):
                with TestClient(backend.app) as client:
                    self.assertEqual(client.get("/health").status_code, 200)
        db.rpc.assert_not_awaited()
        db.client.aclose.assert_awaited_once()

    def test_server_starts_sweeper_and_closes_http_client(self):
        db = AsyncMock()
        with patch.object(backend, "Supabase", return_value=db):
            with TestClient(backend.app) as client:
                self.assertEqual(client.get("/health").json(), {"status": "ok"})
        db.rpc.assert_any_await("sweep_sessions", {}, privileged=True)
        db.client.aclose.assert_awaited_once()


class ContractTests(unittest.TestCase):
    def test_export_matches_current_openapi_and_has_typed_responses(self):
        path = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
        self.assertEqual(json.loads(path.read_text()), backend.app.openapi())
        for route, operations in backend.app.openapi()["paths"].items():
            for operation in operations.values():
                schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
                self.assertIn("$ref", schema, route)

    def test_missing_auth_and_cors_preflight(self):
        client = TestClient(backend.app)
        try:
            response = client.get(f"/sessions/{uuid4()}")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
            preflight = client.options(
                "/sessions",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Authorization,Content-Type",
                },
            )
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(
                preflight.headers["access-control-allow-origin"], "http://localhost:5173"
            )
            denied = client.options(
                "/sessions",
                headers={
                    "Origin": "https://unrelated.example",
                    "Access-Control-Request-Method": "POST",
                },
            )
            self.assertEqual(denied.status_code, 400)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
