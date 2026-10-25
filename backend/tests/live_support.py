"""Opt-in live tests: only uniquely identified fixtures are created or removed."""

import os
import secrets
import unittest
from urllib.parse import urlparse
from uuid import uuid4

import httpx

CURRENT_PROJECT = "jwrfdwwpndlorrmhmwuw"


def test_settings():
    url = os.getenv("TEST_SUPABASE_URL", "").rstrip("/")
    if not url:
        raise unittest.SkipTest("No development TEST_SUPABASE_URL configured; live test not run")
    host = urlparse(url).hostname
    project = os.getenv("TEST_PROJECT_REF", "")
    if host == f"{CURRENT_PROJECT}.supabase.co" and os.getenv("TEST_ALLOW_EXISTING_PROJECT") != "1":
        raise RuntimeError(
            "Set TEST_ALLOW_EXISTING_PROJECT=1 only after confirming this is a development project"
        )
    if (
        not project
        or urlparse(url).scheme != "https"
        or urlparse(url).netloc != f"{project}.supabase.co"
    ):
        raise RuntimeError("TEST_PROJECT_REF must exactly match the development URL hostname")
    if os.getenv("TEST_ALLOW_WRITES") != "1":
        raise RuntimeError("Set TEST_ALLOW_WRITES=1 only for the confirmed development project")
    if not os.getenv("TEST_SUPABASE_SECRET_KEY"):
        raise unittest.SkipTest("TEST_SUPABASE_SECRET_KEY is missing; live test not run")
    return url, os.environ["TEST_SUPABASE_PUBLISHABLE_KEY"], os.environ["TEST_SUPABASE_SECRET_KEY"]


class LiveFixtures:
    def __init__(self, url, key, secret):
        self.url, self.key, self.secret = url, key, secret
        self.run_id = uuid4().hex
        self.users = {}
        self.movie_ids = []
        self.client = httpx.AsyncClient(base_url=url, timeout=20)

    async def request(self, method, path, *, token=None, admin=False, body=None, params=None):
        key = self.secret if admin else self.key
        headers = {"apikey": key}
        if token or (admin and key.startswith("eyJ")):
            headers["Authorization"] = f"Bearer {token or key}"
        response = await self.client.request(
            method, path, headers=headers, json=body, params=params
        )
        # Auth responses contain credentials: never put their bodies in errors/logs.
        if response.is_error:
            raise AssertionError(f"Fixture request {method} {path} failed: {response.status_code}")
        return response.json() if response.content else None

    async def create_users(self):
        for role in ("tv", "alice", "bob", "carol", "outsider"):
            password = secrets.token_urlsafe(32)
            email = f"tandem-test-{self.run_id}-{role}@example.com"
            user = await self.request(
                "POST",
                "/auth/v1/admin/users",
                admin=True,
                body={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                },
            )
            # Register cleanup before the next request can fail.
            self.users[role] = {"id": user["id"]}
            session = await self.request(
                "POST",
                "/auth/v1/token",
                params={
                    "grant_type": "password",
                },
                body={"email": email, "password": password},
            )
            self.users[role].update(session)

    async def seed_movies(self):
        # Only insert unique provider IDs owned by this run; never update catalog data.
        headers = {"apikey": self.secret, "Prefer": "return=representation"}
        if self.secret.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.secret}"
        response = await self.client.post(
            "/rest/v1/movies",
            headers=headers,
            json=[
                {
                    "provider": f"test_{self.run_id}",
                    "provider_movie_id": str(i),
                    "title": f"Test fixture {i}",
                    "trailer_url": "https://example.com/test-trailer",
                    "trailer_provider": "test",
                }
                for i in range(5)
            ],
        )
        if response.status_code != 201:
            raise AssertionError(f"Movie fixture insert failed: {response.status_code}")
        self.movie_ids = [m["id"] for m in response.json()]

    async def cleanup(self):
        failures = []
        # Delete sessions for our generated identities before deleting Auth users.
        for user in self.users.values():
            for method, path, params in (
                ("DELETE", "/rest/v1/group_sessions", {"host_user_id": f"eq.{user['id']}"}),
                ("DELETE", f"/auth/v1/admin/users/{user['id']}", None),
            ):
                try:
                    await self.request(method, path, admin=True, params=params)
                except (AssertionError, httpx.HTTPError):
                    failures.append(f"{method} fixture cleanup")
        try:
            await self.request(
                "DELETE",
                "/rest/v1/movies",
                admin=True,
                params={"provider": f"eq.test_{self.run_id}"},
            )
        except (AssertionError, httpx.HTTPError):
            failures.append("movie fixture cleanup")
        await self.client.aclose()
        if failures:
            raise AssertionError(f"Fixture cleanup incomplete for run {self.run_id}: {failures}")
