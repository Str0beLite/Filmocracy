"""Serve 10 films sampled from the current W's ranking with Gumbel noise (config.TEMPERATURE), so obscure fits surface."""
import random

import numpy as np
import torch
import torch.nn.functional as F

from . import config
from .encoder import embed


@torch.no_grad()
def score_feed(model, x, movie_vecs, prior=None, pos=(), neg=()):
    """Score every film for one feed. pos/neg are the films voted on so far: they pull the predicted taste toward the
    loves and away from the passes right away, so the next rec reacts to votes before W retrains."""
    vecs = torch.from_numpy(movie_vecs)
    y = model(torch.from_numpy(x.copy()))
    if pos or neg:
        d = torch.zeros_like(y)
        if pos:
            d += vecs[sorted(pos)].mean(0)
        if neg:
            d -= 0.5 * vecs[sorted(neg)].mean(0)
        y = F.normalize(y + config.VOTE_PULL * min(len(pos) + len(neg), 10) * d, dim=-1)
    return (y @ vecs.T + model.pop_term(None if prior is None else torch.from_numpy(prior))).numpy()


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
    """Returns [{idx, rank, explore}]: N_RECS films by score + TEMPERATURE * Gumbel noise (sampling from softmax(score/T)
    without replacement). rank is the position in the pure ranking; explore = it would not have made the list without noise."""
    s = scores.astype(np.float64).copy()
    if exclude:
        s[list(exclude)] = -np.inf
    rank = np.empty(len(s), int)
    rank[np.argsort(-s)] = np.arange(len(s))
    noisy = s + config.TEMPERATURE * np.random.default_rng(rng.getrandbits(32)).gumbel(size=len(s))
    chosen = [int(i) for i in np.argsort(-noisy)[: config.N_RECS] if np.isfinite(s[i])]
    return [{"idx": i, "rank": int(rank[i]), "explore": bool(rank[i] >= config.N_RECS)} for i in chosen]
