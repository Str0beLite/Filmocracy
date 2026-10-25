"""The frozen tag encoder E: any tag string -> a 384-number vector. Never trained.

Because tags become vectors, neither side needs a fixed tag list: "gym rat humour" from Muse Spark and
"dark comedy" from the movie database land in the same space, near whatever they mean.
"""
import hashlib
import re
from functools import lru_cache

import numpy as np

from . import config


def unit(x, axis=-1):
    return x / np.maximum(np.linalg.norm(x, axis=axis, keepdims=True), 1e-8)


class FakeEncoder:
    """Bag-of-words hashing into DIM buckets. Lets tests and offline dev run without model weights."""

    def encode(self, texts):
        out = np.zeros((len(texts), config.DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z]+", t.lower()):
                for k in range(8):   # 8 buckets per word, so unrelated words overlap a little, like real embeddings
                    h = int(hashlib.md5(f"{w}/{k}".encode()).hexdigest(), 16)
                    out[i, h % config.DIM] += 1.0 if (h >> 64) & 1 else -1.0
        return unit(out)


class STEncoder:
    def __init__(self, name):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(name, device="cpu")

    def encode(self, texts):
        vecs = self.model.encode(list(texts), normalize_embeddings=True, batch_size=128)
        return np.asarray(vecs, dtype=np.float32)


@lru_cache(maxsize=1)
def get_encoder():
    return FakeEncoder() if config.FAKE_ENCODER else STEncoder(config.EMBED_MODEL)


_cache = {}


def embed(tags):
    """Embed tag strings, caching each one (feeds reuse the same tags a lot)."""
    tags = [t.strip().lower() for t in tags]
    todo = [t for t in dict.fromkeys(tags) if t not in _cache]
    if todo:
        for t, v in zip(todo, get_encoder().encode(todo)):
            _cache[t] = v
    return np.stack([_cache[t] for t in tags]) if tags else np.zeros((0, config.DIM), np.float32)


def bag(weights: dict):
    """{tag: weight} -> one unit vector: the weighted mean of its tag embeddings."""
    if not weights:
        return np.zeros(config.DIM, np.float32)
    tags, w = zip(*weights.items())
    return unit((np.asarray(w, np.float32)[:, None] * embed(tags)).sum(0)).astype(np.float32)
