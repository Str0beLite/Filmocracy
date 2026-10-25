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
        # Popularity prior: squared rank percentile of rating count (ties share the lower rank; no counts -> all 0).
        counts = np.array([m.get("popularity", 0) for m in self.movies])
        self.prior = (np.searchsorted(np.sort(counts), counts) / max(len(counts) - 1, 1)).astype(np.float32) ** 2
        # Recency: release-year rank percentile to the 5th power, 0 = oldest, 1 = newest (films without a year count as
        # mid-catalog). The power makes it rise steeply at the end: only ~8% of the catalog is from 2015-2019.
        years = np.array([int(m["year"]) if str(m.get("year") or "").isdigit() else 0 for m in self.movies])
        known = np.sort(years[years > 0])
        self.recency = np.where(
            years > 0, np.searchsorted(known, years) / max(len(known) - 1, 1), 0.5
        ).astype(np.float32) ** 5

    @classmethod
    def load(cls, path=None):
        path = path or config.CATALOG_DIR
        return cls(json.loads((path / "movies.json").read_text()), np.load(path / "movie_vecs.npy"))

    def feed_vector(self, weights: dict):
        """Any {tag: weight} from Muse Spark -> x, centred like the films. Uncentred feeds were ~95% the same
        generic direction (any two feeds had cosine 0.95), so everyone got the same mainstream picks."""
        return unit(bag(weights) - self.center).astype(np.float32)

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
