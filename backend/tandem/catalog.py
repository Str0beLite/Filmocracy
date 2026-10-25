"""The two tag spaces: Instagram tags (input) and movie tags (output), plus every movie's tag vector."""
import json
from dataclasses import dataclass

import numpy as np

from . import config


def unit(x, axis=-1):
    return x / np.maximum(np.linalg.norm(x, axis=axis, keepdims=True), 1e-8)


@dataclass
class Catalog:
    movies: list            # dicts: id, title, year, ...
    movie_tags: list        # names of the movie-tag dimensions
    ig_tags: list           # names of the Instagram-tag dimensions
    raw: np.ndarray         # (n_movies, n_movie_tags) tag relevance from the database
    w0: np.ndarray          # (n_movie_tags, n_ig_tags) prior translation, before any training

    def __post_init__(self):
        self.raw = self.raw.astype(np.float32)
        self.w0 = self.w0.astype(np.float32)
        # Centre each tag so cosine is driven by what makes a film distinctive, not tags every film has.
        self.tag_mean = self.raw.mean(axis=0)
        self.vecs = unit(self.raw - self.tag_mean)
        self.id_to_idx = {m["id"]: i for i, m in enumerate(self.movies)}
        self.ig_index = {t: i for i, t in enumerate(self.ig_tags)}
        assert self.vecs.shape[1] == len(self.movie_tags) == self.w0.shape[0]
        assert self.w0.shape[1] == len(self.ig_tags)

    @classmethod
    def load(cls, path=None):
        path = path or config.CATALOG_DIR
        read = lambda name: json.loads((path / name).read_text())
        return cls(read("movies.json"), read("movie_tags.json"), read("ig_tags.json"),
                   np.load(path / "movie_tag_matrix.npy"), np.load(path / "w0.npy"))

    def ig_vector(self, weights: dict):
        """{ig_tag: weight} -> unit vector over the IG vocabulary. Unknown tags are ignored."""
        x = np.zeros(len(self.ig_tags), dtype=np.float32)
        for t, w in weights.items():
            if t in self.ig_index:
                x[self.ig_index[t]] = max(float(w), 0.0)
        return unit(x)

    def search(self, q, limit=10):
        q = q.casefold().strip()
        hits = [m for m in self.movies if q in m["title"].casefold()]
        hits.sort(key=lambda m: (m["title"].casefold() != q, -m.get("popularity", 0)))
        return hits[:limit]

    def match_title(self, title):
        hits = self.search(title, limit=1)
        return self.id_to_idx[hits[0]["id"]] if hits else None

    def top_tags(self, idx, k=5):
        return [self.movie_tags[j] for j in np.argsort(-self.vecs[idx])[:k]]

    def public(self, idx):
        m = self.movies[idx]
        return {"id": m["id"], "title": m["title"], "year": m.get("year"), "tmdb_id": m.get("tmdb_id"),
                "tags": self.top_tags(idx)}
