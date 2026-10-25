"""FastAPI app. One process: serving + the background trainer.

Run:  uvicorn tandem.api:app --reload
"""

import asyncio
import json
import math
import zlib
from contextlib import asynccontextmanager
from typing import Literal, Optional

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, vision
from .catalog import Catalog
from .encoder import get_encoder
from .recommend import because_of, pick, score_feed
from .store import Store
from .trainer import Trainer


def create_app(catalog=None, store=None, start_trainer=True, principal=None):
    def anonymous():
        return None

    principal = principal or anonymous
    state = {}

    @asynccontextmanager
    async def lifespan(app):
        state["catalog"] = catalog or Catalog.load()
        state["store"] = store or Store()
        state["trainer"] = Trainer(state["store"], state["catalog"])
        if start_trainer:
            state["trainer"].start()
        get_encoder()  # load encoder weights at boot, not on the first request
        yield
        state["trainer"].stop()

    app = FastAPI(title="tandem", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.state.tandem = state

    def _feed(fid, owner=None):
        f = state["store"].get_feed(fid)
        if not f or (owner is not None and f["user"] != owner):
            raise HTTPException(404, "unknown feed_id")
        return f

    @app.get("/health")
    def health():
        v, _ = state["trainer"].current()
        cat = state["catalog"]
        return {
            "ok": True,
            "w_version": v,
            "movies": len(cat.movies),
            "events": state["store"].count_events(),
            "vision": vision.has_api_key(),
        }

    @app.post("/feeds")
    async def create_feed(
        user: str = Form("anon"),
        tags: str = Form(""),
        files: list[UploadFile] = File(default=[]),
        owner=Depends(principal),
    ):
        """Create a feed from screenshots and/or a JSON tag-weight map."""
        cat = state["catalog"]
        try:
            manual = json.loads(tags) if tags.strip() else {}
            if not isinstance(manual, dict):
                raise ValueError()
            manual = {str(t): float(w) for t, w in manual.items()}
            if any(not math.isfinite(w) for w in manual.values()):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(422, "tags must be a JSON map of numeric weights")
        shots = [(await f.read(), f.content_type or "image/png") for f in files]
        if not manual and not shots:
            raise HTTPException(400, "send at least one screenshot, or tags as JSON")
        weights, dropped = {}, 0
        if shots:
            if not vision.has_api_key():
                raise HTTPException(
                    503, f"screenshots need {config.LLAMA_API_KEY_ENV}; send tags instead"
                )
            weights, dropped = vision.merge(await vision.read_screenshots(shots))
        for t, w in manual.items():
            t = " ".join(str(t).lower().split())
            weights[t] = max(weights.get(t, 0.0), float(w))
        weights = {t: round(w, 3) for t, w in weights.items() if t and w > 0}
        if not weights:
            raise HTTPException(400, "no tags found (everything looked like ads or noise?)")
        x = await asyncio.to_thread(cat.feed_vector, weights)
        fid = state["store"].add_feed(owner or user, weights, x)
        return {
            "feed_id": fid,
            "tags": dict(sorted(weights.items(), key=lambda kv: -kv[1])),
            "dropped_as_noise": dropped,
        }

    class Favourites(BaseModel):
        titles: list[str]
        holdout_frac: float = 0.3  # hide this share for the held-out recall check

    @app.post("/feeds/{fid}/favourites")
    def add_favourites(fid: str, body: Favourites, owner=Depends(principal)):
        """Seed training with films this person already loves. Some are hidden for evaluation."""
        _feed(fid, owner)
        v, _ = state["trainer"].current()
        matched, missing = [], []
        rng = np.random.default_rng(zlib.crc32(fid.encode()))
        for t in body.titles:
            idx = state["catalog"].match_title(t)
            if idx is None:
                missing.append(t)
                continue
            split = "holdout" if rng.random() < body.holdout_frac else "train"
            state["store"].add_event(fid, idx, "favourite", v, split=split)
            matched.append({"title": state["catalog"].movies[idx]["title"], "split": split})
        for _ in matched:
            state["trainer"].notify_event()
        return {"matched": matched, "missing": missing}

    @app.get("/feeds/{fid}/recs")
    def recs(fid: str, owner=Depends(principal)):
        f = _feed(fid, owner)
        cat, store = state["catalog"], state["store"]
        v, model = state["trainer"].current()
        s = score_feed(model, f["x"], cat.vecs)
        items = pick(s, exclude=store.rated_movies(fid))
        ids = store.add_recs(fid, items, v)
        out = [
            {
                "rec_id": rec_id,
                **cat.public(it["idx"]),
                "score": float(s[it["idx"]]),
                "because_of": because_of(model, f["tags"], cat.vecs[it["idx"]]),
            }
            for rec_id, it in zip(ids, items)
        ]
        return {"feed_id": fid, "w_version": v, "recs": out}

    class Feedback(BaseModel):
        rec_id: Optional[int] = None
        feed_id: Optional[str] = None
        movie_id: Optional[int] = None  # MovieLens id (not TMDB or Supabase), outside a rec list
        label: Literal["love", "seen_loved", "nah"]

    @app.post("/feedback")
    def feedback(body: Feedback, owner=Depends(principal)):
        store, cat = state["store"], state["catalog"]
        v, _ = state["trainer"].current()
        if body.rec_id is not None:
            rec = store.get_rec(body.rec_id)
            if not rec:
                raise HTTPException(404, "unknown rec_id")
            fid, idx, v = rec["feed_id"], rec["movie_idx"], rec["w_version"]
        else:
            if body.feed_id is None or body.movie_id not in cat.id_to_idx:
                raise HTTPException(400, "send rec_id, or feed_id + a known movie_id")
            _feed(body.feed_id, owner)
            fid, idx = body.feed_id, cat.id_to_idx[body.movie_id]
        _feed(fid, owner)
        store.add_event(fid, idx, body.label, v, rec_id=body.rec_id)
        state["trainer"].notify_event()
        return {"ok": True, "events": store.count_events()}

    @app.post("/admin/retrain")
    def retrain(owner=Depends(principal)):
        if principal is not anonymous:
            raise HTTPException(403, "Training is disabled in the unified backend")
        """Force a round now (handy on stage)."""
        res = state["trainer"].retrain()
        return res or {"skipped": "no training data yet"}

    @app.get("/model")
    def model_info(owner=Depends(principal)):
        """Current W version + every round's held-out recall, for the live chart."""
        v, _ = state["trainer"].current()
        return {"w_version": v, "recall_k": config.RECALL_K, "history": state["store"].models()}

    @app.get("/movies/search")
    def search(q: str, limit: int = 10, owner=Depends(principal)):
        return [
            state["catalog"].public(state["catalog"].id_to_idx[m["id"]])
            for m in state["catalog"].search(q, limit)
        ]

    return app


app = create_app()
