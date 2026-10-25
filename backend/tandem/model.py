"""The trained part: W maps a feed's tag vector to a predicted film-taste vector.

    ŷ = normalize(W x),   W = I + A Bᵀ,   score(m) = ŷ · t_m

x is the weighted mean embedding of the feed's tags (any tags Muse Spark wrote), t_m the same for a film's
tags from the database. Both live in the encoder's 384-dim space, so W is 384×384 whatever the tag
counts are. A starts at zero, so day 0 is W = I: match tags by meaning. A Bᵀ is low rank (~6k params)
so a handful of users can't wreck it.
"""
import torch
import torch.nn.functional as F

from . import config


class Translator(torch.nn.Module):
    def __init__(self, w0, rank=config.RANK):
        super().__init__()
        self.register_buffer("W0", torch.as_tensor(w0, dtype=torch.float32))
        n_out, n_in = self.W0.shape
        self.A = torch.nn.Parameter(torch.zeros(n_out, rank))
        self.B = torch.nn.Parameter(torch.randn(n_in, rank) * 0.01)

    def W(self):
        return self.W0 + self.A @ self.B.T

    def forward(self, x):                       # x: (..., DIM) feed vector -> predicted film taste (..., DIM)
        return F.normalize(x @ self.W0.T + (x @ self.B) @ self.A.T, dim=-1)

    def reg(self):
        return (self.A @ self.B.T).pow(2).sum()


def scores(model, x, movies):
    """Cosine between the predicted film taste and every movie's tag vector."""
    return model(x) @ movies.T


def taste_target(movies, pos, neg):
    """The user's 'trained film taste': mean tag vector of films they love, nudged away from ones they don't."""
    y = movies[sorted(pos)].mean(0)
    if neg:
        y = y - 0.5 * movies[sorted(neg)].mean(0)
    return F.normalize(y, dim=-1)


def loss_fn(model, feeds, examples, movies, tau=config.TAU, beta=config.BETA, lam=config.LAMBDA,
            hard_w=config.HARD_NEG_WEIGHT):
    """
    feeds:    {feed_id: {"x": (n_ig,) tensor, "pos": set(idx), "neg": set(idx)}}
    examples: [(feed_id, positive_idx)]   (the training positives; held-out ones are left out)

    Three terms:
      1. taste:   1 - cos(W x, y_u)  — land on the user's film-taste vector from their IG vector alone.
      2. ranking: InfoNCE over the whole catalog — loved films above every other film. Thumbs-downs are
                  hard negatives (up-weighted) plus an unlikelihood term.
      3. λ‖A Bᵀ‖² — stay near the prior where there's no data.
    """
    log_hard = torch.log(torch.tensor(hard_w))
    by_feed = {}
    for fid, j in examples:
        by_feed.setdefault(fid, []).append(j)
    taste_terms, ce_terms, unlike_terms = [], [], []
    for fid, f in feeds.items():
        mine = by_feed.get(fid, [])
        if not mine and not f["neg"]:
            continue
        pred = model(f["x"])
        logits = (pred @ movies.T) / tau
        neg = torch.tensor(sorted(f["neg"]), dtype=torch.long)
        if mine:
            taste_terms.append(1 - pred @ taste_target(movies, set(mine), f["neg"]))
            boosted = logits.clone()
            if len(neg):
                boosted[neg] = boosted[neg] + log_hard
            for j in mine:
                row = boosted.clone()
                others = [p for p in f["pos"] if p != j]
                if others:                       # don't punish the model for scoring other loves highly
                    row[torch.tensor(others)] = float("-inf")
                ce_terms.append(F.cross_entropy(row[None], torch.tensor([j])))
        if len(neg):
            p_neg = F.softmax(logits, dim=0)[neg]
            unlike_terms.append(-torch.log1p(-p_neg.clamp(max=1 - 1e-6)).mean())
    mean = lambda ts: torch.stack(ts).mean() if ts else torch.zeros(())
    return beta * mean(taste_terms) + mean(ce_terms) + 0.5 * mean(unlike_terms) + lam * model.reg()


@torch.no_grad()
def recall_at_k(model, feeds, examples, movies, k=config.RECALL_K):
    """Fraction of held-out (feed, loved film) pairs where the film lands in the top k."""
    if not examples:
        return None
    hits, cache = 0, {}
    for fid, j in examples:
        if fid not in cache:
            cache[fid] = scores(model, feeds[fid]["x"], movies)
        s = cache[fid]
        hits += int((s >= s[j]).sum().item() - 1 < k)   # ties count against us
    return hits / len(examples)


def state(model):
    return {"A": model.A.detach().clone(), "B": model.B.detach().clone()}


def from_state(w0, st):
    m = Translator(w0, rank=st["A"].shape[1])
    with torch.no_grad():
        m.A.copy_(st["A"])
        m.B.copy_(st["B"])
    return m
