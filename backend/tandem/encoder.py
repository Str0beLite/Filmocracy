"""The frozen text encoder E. Never trained; same model for reels and movies."""
import hashlib
import re
from functools import lru_cache

import numpy as np

from . import config


class FakeEncoder:
    """Bag-of-words hashing into DIM buckets. Lets tests and offline dev run without model weights."""

    def encode(self, texts):
        out = np.zeros((len(texts), config.DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z]+", t.lower()):
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                out[i, h % config.DIM] += 1.0 if (h >> 64) & 1 else -1.0
        return _normalize(out)


class STEncoder:
    def __init__(self, name):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(name, device="cpu")

    def encode(self, texts):
        vecs = self.model.encode(list(texts), normalize_embeddings=True, batch_size=64)
        return np.asarray(vecs, dtype=np.float32)


def _normalize(x):
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-8)


@lru_cache(maxsize=1)
def get_encoder():
    return FakeEncoder() if config.FAKE_ENCODER else STEncoder(config.EMBED_MODEL)
