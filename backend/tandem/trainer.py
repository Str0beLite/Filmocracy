"""Live training loop: retrain W on the whole replay buffer, gate on held-out recall, hot-swap.

Runs in a background thread inside the API process. The trained part of W is ~6k parameters, so a retrain over a few
hundred events takes seconds on CPU and needs no GPU or separate worker.
"""
import math
import threading
import time

import torch

from . import config
from .model import Translator, from_state, loss_fn, recall_at_k, state


class Trainer:
    def __init__(self, store, catalog):
        self.store = store
        self.movies = torch.from_numpy(catalog.vecs)
        self.w0 = catalog.w0
        self.version = 0
        self.model = Translator(self.w0)     # version 0 = W0 = identity, no training yet
        self.model.eval()
        self._load_latest()
        self._pending = 0
        self._wake = threading.Event()
        self._train_lock = threading.Lock()
        self._stop = False
        self.thread = None

    def _load_latest(self):
        row = self.store.latest_accepted()
        if row:
            self.model = from_state(self.w0, torch.load(row["path"]))
            self.model.eval()
            self.version = row["version"]

    # background thread
    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True, name="trainer")
        self.thread.start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def notify_event(self):
        self._pending += 1
        if self._pending >= config.RETRAIN_EVERY:
            self._wake.set()

    def _loop(self):
        while not self._stop:
            self._wake.wait()
            self._wake.clear()
            if self._stop:
                break
            try:
                self.retrain()
            except Exception as e:  # noqa: BLE001 - never let a bad round kill serving
                print(f"[trainer] retrain failed: {e!r}")

    # data
    def build_dataset(self):
        events = self.store.events()
        feed_vecs = self.store.all_feed_vectors()
        feeds, positives = {}, []
        for e in events:
            if e["feed_id"] not in feed_vecs:
                continue
            f = feeds.setdefault(e["feed_id"], {"x": torch.from_numpy(feed_vecs[e["feed_id"]].copy()),
                                                "pos": set(), "neg": set()})
            if e["label"] in config.POSITIVE_LABELS:
                f["pos"].add(e["movie_idx"])
                positives.append(e)
            elif e["label"] in config.NEGATIVE_LABELS:
                f["neg"].add(e["movie_idx"])

        # Held-out = hidden favourites + the newest 10% of live positives.
        hidden = [e for e in positives if e["split"] == "holdout"]
        live = [e for e in positives if e["split"] != "holdout"]
        n_new = math.ceil(len(live) * config.HOLDOUT_NEWEST_FRAC) if len(live) >= 10 else 0
        newest = live[len(live) - n_new:] if n_new else []
        train = live[:len(live) - n_new]
        pair = lambda e: (e["feed_id"], e["movie_idx"])
        return feeds, [pair(e) for e in train], [pair(e) for e in hidden + newest], len(events)

    # one round
    def retrain(self, steps=config.TRAIN_STEPS):
        with self._train_lock:
            self._pending = 0
            feeds, train, holdout, n_events = self.build_dataset()
            if not train and not any(f["neg"] for f in feeds.values()):
                return None

            cand = from_state(self.w0, state(self.model))   # warm start from the live W
            cand.train()
            opt = torch.optim.Adam(cand.parameters(), lr=config.LR)
            t0 = time.time()
            for _ in range(steps):
                opt.zero_grad()
                loss = loss_fn(cand, feeds, train, self.movies)
                loss.backward()
                opt.step()
            cand.eval()

            r_new = recall_at_k(cand, feeds, holdout, self.movies)
            r_old = recall_at_k(self.model, feeds, holdout, self.movies)
            accepted = r_new is None or r_new >= r_old

            version = max([m["version"] for m in self.store.models()] + [self.version]) + 1
            config.CKPT_DIR.mkdir(parents=True, exist_ok=True)
            path = config.CKPT_DIR / f"w_v{version}.pt"
            torch.save(state(cand), path)
            self.store.add_model(version=version, created=time.time(), path=str(path), accepted=int(accepted),
                                 recall_new=r_new, recall_old=r_old, n_train=len(train), n_holdout=len(holdout),
                                 n_events=n_events, loss=float(loss.item()))
            if accepted:                            # hot-swap: one reference assignment, readers never see a half-updated W
                self.model, self.version = cand, version
            print(f"[trainer] v{version} {'ACCEPTED' if accepted else 'rejected'} "
                  f"recall@{config.RECALL_K} {r_old} -> {r_new} ({len(train)} train, {len(holdout)} held out, "
                  f"{time.time() - t0:.1f}s)")
            return {"version": version, "accepted": accepted, "recall_new": r_new, "recall_old": r_old,
                    "n_train": len(train), "n_holdout": len(holdout)}

    def current(self):
        return self.version, self.model
