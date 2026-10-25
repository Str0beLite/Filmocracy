"""The trained part: a low-rank translator W = I + A Bᵀ between the frozen encoder and cosine scoring.

A starts at zero, so an untrained Translator returns exactly the zero-shot ranking.
"""
import torch
import torch.nn.functional as F

from . import config


class Translator(torch.nn.Module):
    def __init__(self, d=config.DIM, rank=config.RANK):
        super().__init__()
        self.A = torch.nn.Parameter(torch.zeros(d, rank))
        self.B = torch.nn.Parameter(torch.randn(d, rank) * 0.01)

    def forward(self, r):                       # r: (n_reels, d)
        return F.normalize(r + (r @ self.B) @ self.A.T, dim=-1)

    def reg(self):
        return (self.A @ self.B.T).pow(2).sum()


def user_scores(model, reels, movies, tau=config.TAU):
    """s(u, m) = τ · logsumexp_i(cos(W rᵢ, m) / τ): a soft max over reels, so one strong facet can carry a match."""
    sims = model(reels) @ movies.T              # (n_reels, n_movies)
    return tau * torch.logsumexp(sims / tau, dim=0)


def loss_fn(model, feeds, examples, movies, tau=config.TAU, lam=config.LAMBDA, hard_w=config.HARD_NEG_WEIGHT):
    """
    feeds:    {feed_id: {"reels": (n, d) tensor, "pos": set(idx), "neg": set(idx)}}
    examples: [(feed_id, positive_idx)]
    InfoNCE over the whole catalog: every other movie is a negative for free. Thumbs-downs are hard
    negatives (up-weighted in the softmax) and also get an unlikelihood term so feeds with only
    thumbs-downs still teach something.
    """
    log_hard = torch.log(torch.tensor(hard_w))
    ce_terms, unlike_terms = [], []
    for fid, f in feeds.items():
        mine = [j for g, j in examples if g == fid]
        if not mine and not f["neg"]:
            continue
        logits = user_scores(model, f["reels"], movies, tau) / tau
        neg = torch.tensor(sorted(f["neg"]), dtype=torch.long)
        boosted = logits.clone()
        if len(neg):
            boosted[neg] = boosted[neg] + log_hard
        for j in mine:
            others = [p for p in f["pos"] if p != j]
            row = boosted.clone()
            if others:                           # don't punish the model for scoring other loves highly
                row[torch.tensor(others)] = float("-inf")
            ce_terms.append(F.cross_entropy(row[None], torch.tensor([j])))
        if len(neg):
            p_neg = F.softmax(logits, dim=0)[neg]
            unlike_terms.append(-torch.log1p(-p_neg.clamp(max=1 - 1e-6)).mean())
    zero = torch.zeros(())
    ce = torch.stack(ce_terms).mean() if ce_terms else zero
    unlike = torch.stack(unlike_terms).mean() if unlike_terms else zero
    return ce + 0.5 * unlike + lam * model.reg()


@torch.no_grad()
def recall_at_k(model, feeds, examples, movies, k=config.RECALL_K):
    """Fraction of held-out (feed, loved film) pairs where the film lands in the top k."""
    if not examples:
        return None
    hits = 0
    cache = {}
    for fid, j in examples:
        if fid not in cache:
            cache[fid] = user_scores(model, feeds[fid]["reels"], movies)
        s = cache[fid]
        hits += int((s > s[j]).sum().item() < k)
    return hits / len(examples)


def state(model):
    return {"A": model.A.detach().clone(), "B": model.B.detach().clone()}


def from_state(st):
    m = Translator(d=st["A"].shape[0], rank=st["A"].shape[1])
    with torch.no_grad():
        m.A.copy_(st["A"])
        m.B.copy_(st["B"])
    return m
