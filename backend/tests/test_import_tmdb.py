import unittest

import httpx

from import_tmdb import collect_movies, insert_movies, movie_row, request


class ImportTests(unittest.TestCase):
    def test_requires_trailer_and_prefers_official(self):
        details = {
            "id": 12,
            "title": "Movie",
            "runtime": 0,
            "release_date": "",
            "videos": {
                "results": [
                    {"type": "Trailer", "site": "YouTube", "key": "unofficial", "official": False},
                    {"type": "Trailer", "site": "YouTube", "key": "official", "official": True},
                ],
            },
        }
        row = movie_row(details, "https://image.tmdb.org/t/p/")
        self.assertEqual(row["trailer_url"], "https://www.youtube.com/watch?v=official")
        self.assertIsNone(row["runtime_minutes"])
        self.assertIsNone(row["release_date"])
        details["videos"]["results"] = [{"type": "Teaser", "site": "YouTube", "key": "teaser"}]
        self.assertIsNone(movie_row(details, "https://image.tmdb.org/t/p/"))

    def test_insert_is_idempotent_and_does_not_update_existing_data(self):
        stored = {("tmdb", "1"): {"title": "Existing hand-edited title"}}

        def handler(req):
            import json

            self.assertEqual(req.method, "POST")
            self.assertIn("resolution=ignore-duplicates", req.headers["Prefer"])
            inserted = []
            for row in json.loads(req.content):
                key = (row["provider"], row["provider_movie_id"])
                if key not in stored:
                    stored[key] = row
                    inserted.append(row)
            return httpx.Response(201, json=inserted)

        rows = [
            {"provider": "tmdb", "provider_movie_id": str(i), "title": "Import"} for i in (1, 2)
        ]
        with httpx.Client(
            base_url="https://test", transport=httpx.MockTransport(handler)
        ) as client:
            self.assertEqual(insert_movies(client, rows)["inserted"], 1)
            self.assertEqual(insert_movies(client, rows)["inserted"], 0)
        self.assertEqual(stored[("tmdb", "1")]["title"], "Existing hand-edited title")

    def test_collects_100_unique_trailer_movies_without_database_calls(self):
        def handler(req):
            if req.url.path.endswith("configuration"):
                return httpx.Response(
                    200,
                    json={
                        "images": {
                            "secure_base_url": "https://image.tmdb.org/t/p/",
                        }
                    },
                )
            if "discover" in req.url.path:
                return httpx.Response(
                    200, json={"total_pages": 1, "results": [{"id": i} for i in range(100)]}
                )
            return httpx.Response(
                200,
                json={
                    "id": int(req.url.path.split("/")[-1]),
                    "title": "Fixture",
                    "videos": {
                        "results": [
                            {"type": "Trailer", "site": "YouTube", "key": "fixture"},
                        ]
                    },
                },
            )

        with httpx.Client(
            base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(handler)
        ) as client:
            self.assertEqual(len(collect_movies(client, 100, sleep=lambda _: None)), 100)

    def test_429_retries_are_bounded_and_honor_retry_after(self):
        waits = []
        with httpx.Client(
            base_url="https://test",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "2"})
            ),
        ) as client:
            with self.assertRaises(RuntimeError):
                request(client, "GET", "/configuration", sleep=waits.append)
        self.assertEqual(waits, [2, 2, 2])
