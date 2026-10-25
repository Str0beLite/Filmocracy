"""The movie side: metadata + precomputed, normalized profile vectors m."""
import json
from dataclasses import dataclass

import numpy as np

from . import config


@dataclass
class Catalog:
    movies: list           # dicts: id (tmdb), title, year, overview, genres, vote_count, profile
    vecs: np.ndarray       # (n_movies, DIM) float32, unit length
    id_to_idx: dict

    @classmethod
    def load(cls, path=None):
        path = path or config.CATALOG_DIR
        movies = json.loads((path / "movies.json").read_text())
        vecs = np.load(path / "movie_vecs.npy").astype(np.float32)
        assert len(movies) == len(vecs), "movies.json and movie_vecs.npy are out of sync; rebuild the catalog"
        return cls(movies, vecs, {m["id"]: i for i, m in enumerate(movies)})

    def recommendable_mask(self):
        return np.array([m.get("vote_count", 0) >= config.MIN_VOTES for m in self.movies])

    def search(self, q, limit=10):
        q = q.casefold().strip()
        hits = [m for m in self.movies if q in m["title"].casefold()]
        hits.sort(key=lambda m: (m["title"].casefold() != q, -m.get("vote_count", 0)))
        return hits[:limit]

    def match_title(self, title):
        hits = self.search(title, limit=1)
        return self.id_to_idx[hits[0]["id"]] if hits else None

    def public(self, idx):
        m = self.movies[idx]
        return {k: m.get(k) for k in ("id", "title", "year", "overview", "genres", "profile")}
