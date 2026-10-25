"""The movie side: each film's tags from the database, and its tag-embedding vector t_m."""
import json
from dataclasses import dataclass

import numpy as np

from . import config
from .encoder import bag, unit


@dataclass
class Catalog:
    movies: list            # dicts: id, title, year, tmdb_id?, tags {tag: weight}
    raw: np.ndarray         # (n_movies, DIM) weighted mean tag embedding per film, unit length

    def __post_init__(self):
        self.raw = unit(self.raw.astype(np.float32))
        # Centre on the "generic film": cosine then rewards what makes a film distinctive, not tags every film has.
        self.center = self.raw.mean(axis=0)
        self.vecs = unit(self.raw - self.center).astype(np.float32)
        self.id_to_idx = {m["id"]: i for i, m in enumerate(self.movies)}
        self.w0 = np.eye(config.DIM, dtype=np.float32)   # day 0: W = I, pure tag-meaning match

    @classmethod
    def load(cls, path=None):
        path = path or config.CATALOG_DIR
        return cls(json.loads((path / "movies.json").read_text()), np.load(path / "movie_vecs.npy"))

    def feed_vector(self, weights: dict):
        """Any {tag: weight} from Muse Spark -> x. Not centred: subtracting the film centre would make an
        unrelated feed point away from "generic film" and pull up oddballs for no reason."""
        return bag(weights)

    def search(self, q, limit=10):
        q = q.casefold().strip()
        hits = [m for m in self.movies if q in m["title"].casefold()]
        hits.sort(key=lambda m: (m["title"].casefold() != q, -m.get("popularity", 0)))
        return hits[:limit]

    def match_title(self, title):
        hits = self.search(title, limit=1)
        return self.id_to_idx[hits[0]["id"]] if hits else None

    def top_tags(self, idx, k=5):
        tags = self.movies[idx].get("tags", {})
        return sorted(tags, key=lambda t: -tags[t])[:k]

    def public(self, idx):
        m = self.movies[idx]
        return {"id": m["id"], "title": m["title"], "year": m.get("year"), "tmdb_id": m.get("tmdb_id"),
                "tags": self.top_tags(idx)}
