"""Serve 10 films: 8 best by the current W, plus 2 exploration picks from ranks 11–50."""
import random

import numpy as np
import torch

from . import config
from .encoder import embed
from .model import scores


@torch.no_grad()
def score_feed(model, x, movie_vecs):
    return scores(model, torch.from_numpy(x.copy()), torch.from_numpy(movie_vecs)).numpy()


@torch.no_grad()
def because_of(model, tags, movie_vec, k=3):
    """Which of the feed's tags pushed this film up most: contribution = w · (W e_tag) · t_m."""
    if not tags:
        return []
    names = list(tags)
    w = np.array([tags[t] for t in names], np.float32)
    W = model.W().numpy()
    contrib = w * ((embed(names) @ W.T) @ movie_vec)
    return [names[j] for j in np.argsort(-contrib)[:k] if contrib[j] > 0]


def boost(scores, movies, tags):
    """Add TAG_BOOST to every film whose stored tags include any of `tags` (lowercased, whitespace collapsed)."""
    wanted = {" ".join(str(t).lower().split()) for t in tags} - {""}
    if not wanted:
        return scores
    hit = np.array([bool(wanted & m.get("tags", {}).keys()) for m in movies])
    return scores + config.TAG_BOOST * hit


def pick(scores, exclude=(), rng=random):
    """Returns [{idx, rank, explore}], where rank is the position in the pure model ranking."""
    s = scores.astype(np.float64).copy()
    if exclude:
        s[list(exclude)] = -np.inf
    order = [int(i) for i in np.argsort(-s) if np.isfinite(s[i])]
    n_best = config.N_RECS - config.N_EXPLORE
    best = [{"idx": i, "rank": r, "explore": False} for r, i in enumerate(order[:n_best])]
    lo, hi = config.EXPLORE_RANKS
    pool = list(range(max(lo, n_best), min(hi, len(order))))
    explore = [{"idx": order[r], "rank": r, "explore": True} for r in rng.sample(pool, min(config.N_EXPLORE, len(pool)))]
    out = list(best)
    for e in explore:  # tuck exploration picks in below the top 2 so they don't look like filler at the end
        out.insert(rng.randint(min(2, len(out)), len(out)), e)
    return out
