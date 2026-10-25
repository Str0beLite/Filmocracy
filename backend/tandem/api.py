"""FastAPI app. One process: serving + the background trainer.

Run:  uvicorn tandem.api:app --reload
"""
import json
import zlib
from contextlib import asynccontextmanager
from typing import Literal, Optional

import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, profiles
from .catalog import Catalog
from .encoder import get_encoder
from .recommend import pick, score_feed
from .store import Store
from .trainer import Trainer


def create_app(catalog=None, store=None, start_trainer=True):
    state = {}

    @asynccontextmanager
    async def lifespan(app):
        state["catalog"] = catalog or Catalog.load()
        state["store"] = store or Store()
        state["mask"] = state["catalog"].recommendable_mask()
        state["trainer"] = Trainer(state["store"], state["catalog"])
        if start_trainer:
            state["trainer"].start()
        get_encoder()  # load weights at boot, not on the first request
        yield
        state["trainer"].stop()

    app = FastAPI(title="tandem", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.tandem = state

    def _feed(fid):
        f = state["store"].get_feed(fid)
        if not f:
            raise HTTPException(404, "unknown feed_id")
        return f

    @app.get("/health")
    def health():
        v, _ = state["trainer"].current()
        return {"ok": True, "w_version": v, "movies": len(state["catalog"].movies),
                "events": state["store"].count_events(), "llm": profiles.has_api_key()}

    @app.post("/feeds")
    async def create_feed(user: str = Form("anon"), captions: str = Form(""),
                          files: list[UploadFile] = File(default=[])):
        """Upload reel screenshots and/or captions (newline-separated or a JSON list). Returns a feed_id."""
        caps = _parse_captions(captions)
        shots = [(await f.read(), f.content_type or "image/png") for f in files]
        if not caps and not shots:
            raise HTTPException(400, "send at least one screenshot or caption")
        if profiles.has_api_key():
            reels = await profiles.profile_reels(shots, caps)
            kept = [r for r in reels if not r.is_ad_or_noise]
            dropped = len(reels) - len(kept)
            reel_rows = [{"summary": r.caption_summary, "profile": r.to_text()} for r in kept]
        else:
            if shots:
                raise HTTPException(503, "screenshots need ANTHROPIC_API_KEY; send captions instead")
            dropped, reel_rows = 0, [{"summary": c[:80], "profile": c} for c in caps]
        if not reel_rows:
            raise HTTPException(400, "everything looked like ads or noise")
        vecs = get_encoder().encode([r["profile"] for r in reel_rows])
        fid = state["store"].add_feed(user, reel_rows, vecs)
        return {"feed_id": fid, "reels": reel_rows, "dropped_as_noise": dropped}

    class Favourites(BaseModel):
        titles: list[str]
        holdout_frac: float = 0.3   # hide this share for the held-out recall check

    @app.post("/feeds/{fid}/favourites")
    def add_favourites(fid: str, body: Favourites):
        """Seed training with films this person already loves. Some are hidden for evaluation."""
        _feed(fid)
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
    def recs(fid: str):
        f = _feed(fid)
        cat, store = state["catalog"], state["store"]
        v, model = state["trainer"].current()
        scores = score_feed(model, f["vecs"], cat.vecs)
        items = pick(scores, state["mask"], exclude=store.rated_movies(fid))
        ids = store.add_recs(fid, items, v)
        # Cheap "why": the reel that matched each film best.
        with torch.no_grad():
            r = model(torch.from_numpy(f["vecs"].copy())).numpy()
        out = []
        for rec_id, it in zip(ids, items):
            best = int(np.argmax(r @ cat.vecs[it["idx"]]))
            out.append({"rec_id": rec_id, **cat.public(it["idx"]), "score": float(scores[it["idx"]]),
                        "because_of_reel": f["profiles"][best]["summary"]})
        return {"feed_id": fid, "w_version": v, "recs": out}

    class Feedback(BaseModel):
        rec_id: Optional[int] = None
        feed_id: Optional[str] = None
        movie_id: Optional[int] = None    # TMDB id, for feedback outside a rec list
        label: Literal["love", "seen_loved", "nah"]

    @app.post("/feedback")
    def feedback(body: Feedback):
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
            _feed(body.feed_id)
            fid, idx = body.feed_id, cat.id_to_idx[body.movie_id]
        store.add_event(fid, idx, body.label, v, rec_id=body.rec_id)
        state["trainer"].notify_event()
        return {"ok": True, "events": store.count_events()}

    @app.post("/admin/retrain")
    def retrain():
        """Force a round now (handy on stage)."""
        res = state["trainer"].retrain()
        return res or {"skipped": "no training data yet"}

    @app.get("/model")
    def model_info():
        """Current W version + every round's held-out recall, for the live chart."""
        v, _ = state["trainer"].current()
        return {"w_version": v, "recall_k": config.RECALL_K, "history": state["store"].models()}

    @app.get("/movies/search")
    def search(q: str, limit: int = 10):
        return [state["catalog"].public(state["catalog"].id_to_idx[m["id"]]) for m in state["catalog"].search(q, limit)]

    return app


def _parse_captions(s):
    s = s.strip()
    if not s:
        return []
    if s.startswith("["):
        return [c for c in json.loads(s) if str(c).strip()]
    return [c.strip() for c in s.splitlines() if c.strip()]


app = create_app()
