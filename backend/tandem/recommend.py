"""Serve 10 films: 8 best by the current W, plus 2 exploration picks from ranks 11–50."""
import random

import numpy as np
import torch

from . import config
from .model import scores


@torch.no_grad()
def score_feed(model, x, movie_vecs):
    return scores(model, torch.from_numpy(x.copy()), torch.from_numpy(movie_vecs)).numpy()


@torch.no_grad()
def because_of(model, x, movie_vec, ig_tags, k=3):
    """Which of the user's IG tags pushed this film up most: contribution_j = x_j · (W[:, j] · t_m)."""
    contrib = x * (model.W().numpy().T @ movie_vec)
    return [ig_tags[j] for j in np.argsort(-contrib)[:k] if contrib[j] > 0]


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
