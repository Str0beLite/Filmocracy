"""FastAPI app. One process: serving + the background trainer.

Run:  uvicorn tandem.api:app --reload --env-file .env
"""
import json
import uuid
import zlib
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, grid, vision
from .auth import current_user, require_admin
from .catalog import Catalog
from .encoder import get_encoder, unit
from .recommend import because_of, boost, pick, score_feed
from .store import Store
from .trainer import Trainer


def create_app(catalog=None, store=None, start_trainer=True):
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
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.tandem = state
    # shortcut: groups live in memory and are lost on restart; move to SQLite if sessions must survive deploys.
    state["groups"] = {}

    def _feed(fid, user):
        f = state["store"].get_feed(fid)
        if not f:
            raise HTTPException(404, "unknown feed_id")
        if f["user"] != user:
            raise HTTPException(403, "not your feed")
        return f

    def _recs(f, boost_tags=(), exclude=()):
        """10 recs for one feed's x, logged under that feed so feedback and exploration work as usual."""
        cat, store = state["catalog"], state["store"]
        v, model = state["trainer"].current()
        s = boost(score_feed(model, f["x"], cat.vecs), cat.movies, boost_tags)
        items = pick(s, exclude=store.rated_movies(f["id"]) | set(exclude))
        ids = store.add_recs(f["id"], items, v)
        return v, [{"rec_id": rec_id, **cat.public(it["idx"]), "score": float(s[it["idx"]]),
                    "because_of": because_of(model, f["tags"], cat.vecs[it["idx"]])}
                   for rec_id, it in zip(ids, items)]

    @app.get("/health")
    def health():
        v, _ = state["trainer"].current()
        cat = state["catalog"]
        return {"ok": True, "w_version": v, "movies": len(cat.movies), "events": state["store"].count_events(),
                "vision": vision.has_api_key()}

    @app.post("/feeds")
    async def create_feed(tags: str = Form(""), files: Annotated[list[UploadFile], File()] = (),
                          user: str = Depends(current_user)):
        """Upload feed screenshots (Explore pages are split into tiles, each read by Muse Spark) and/or a JSON {tag: weight} map. Returns a feed_id."""
        cat = state["catalog"]
        manual = json.loads(tags) if tags.strip() else {}
        shots = []
        for f in files:   # an Explore screenshot becomes one shot per tile; anything else stays whole
            data = await f.read()
            shots += grid.split_explore(data) or [(data, f.content_type or "image/png")]
        if not manual and not shots:
            raise HTTPException(400, "send at least one screenshot, or tags as JSON")
        weights, dropped = {}, 0
        if shots:
            if not vision.has_api_key():
                raise HTTPException(503, f"screenshots need {config.MUSE_API_KEY_ENV}; send tags instead")
            weights, dropped = vision.merge(await vision.read_screenshots(shots))
        for t, w in manual.items():
            t = " ".join(str(t).lower().split())
            weights[t] = max(weights.get(t, 0.0), float(w))
        weights = {t: round(w, 3) for t, w in weights.items() if t and w > 0}
        if not weights:
            raise HTTPException(400, "no tags found (everything looked like ads or noise?)")
        x = cat.feed_vector(weights)
        fid = state["store"].add_feed(user, weights, x)
        return {"feed_id": fid, "tags": dict(sorted(weights.items(), key=lambda kv: -kv[1])),
                "dropped_as_noise": dropped}

    @app.get("/me")
    def me(user: str = Depends(current_user)):
        """The caller's latest feed. feed_id null = send them to onboarding (upload screenshots)."""
        f = state["store"].latest_feed(user)
        return {"user": user, "feed_id": f["id"], "tags": f["tags"]} if f else {"user": user, "feed_id": None}

    class Favourites(BaseModel):
        titles: list[str] = []
        movie_ids: list[int] = []   # exact catalog ids, when the client already knows the film
        holdout_frac: float = 0.3   # hide this share for the held-out recall check

    @app.post("/feeds/{fid}/favourites")
    def add_favourites(fid: str, body: Favourites, user: str = Depends(current_user)):
        """Seed training with films this person already loves. Some are hidden for evaluation."""
        _feed(fid, user)
        v, _ = state["trainer"].current()
        matched, missing = [], []
        cat = state["catalog"]
        wanted = [(t, cat.match_title(t)) for t in body.titles] + [(m, cat.id_to_idx.get(m)) for m in body.movie_ids]
        for t, idx in wanted:
            if idx is None:
                missing.append(t)
                continue
            # seeded per film so favourites added one at a time still split ~holdout_frac
            r = np.random.default_rng(zlib.crc32(f"{fid}/{idx}".encode())).random()
            split = "holdout" if r < body.holdout_frac else "train"
            state["store"].add_event(fid, idx, "favourite", v, split=split)
            matched.append({"id": cat.movies[idx]["id"], "title": cat.movies[idx]["title"], "split": split})
        for _ in matched:
            state["trainer"].notify_event()
        return {"matched": matched, "missing": missing}

    @app.get("/feeds/{fid}/recs")
    def recs(fid: str, boost: Annotated[list[str], Query()] = (), user: str = Depends(current_user)):
        v, out = _recs(_feed(fid, user), boost)
        return {"feed_id": fid, "w_version": v, "recs": out}

    # Group session: the host's big screen creates it, phones join via QR code. A member's embedding is
    # their latest feed's x; it never leaves the server, so every call scores with the live W.
    class NewGroup(BaseModel):
        user_ids: list[str] = []

    def _group(gid, user):
        g = state["groups"].get(gid)
        if not g:
            raise HTTPException(404, "unknown group_id")
        if user != g["host"] and user not in g["members"]:
            raise HTTPException(403, "not in this group")
        return g

    def _add_members(g, user_ids):
        feeds = {u: state["store"].latest_feed(u) for u in user_ids}
        missing = [u for u, f in feeds.items() if f is None]
        if missing:
            raise HTTPException(409, {"needs_onboarding": missing})
        g["members"].update(feeds)
        g["avg_x"] = unit(np.mean([f["x"] for f in g["members"].values()], axis=0)).astype(np.float32)

    def _group_out(gid, g):
        return {"group_id": gid, "host": g["host"], "members": list(g["members"])}

    @app.post("/groups")
    def create_group(body: NewGroup, user: str = Depends(current_user)):
        """The caller is the host (not a member unless listed). Members need a feed already."""
        g = {"host": user, "members": {}, "avg_x": None}
        if body.user_ids:
            _add_members(g, body.user_ids)
        gid = uuid.uuid4().hex[:8]
        state["groups"][gid] = g
        return _group_out(gid, g)

    @app.post("/groups/{gid}/join")
    def join_group(gid: str, user: str = Depends(current_user)):
        g = state["groups"].get(gid)
        if not g:
            raise HTTPException(404, "unknown group_id")
        _add_members(g, [user])
        return _group_out(gid, g)

    @app.get("/groups/{gid}")
    def get_group(gid: str, user: str = Depends(current_user)):
        return _group_out(gid, _group(gid, user))

    class GroupRecsReq(BaseModel):
        boost: list[str] = []      # tags to push up (e.g. the mood the host picked)
        exclude: list[int] = []    # movie ids to skip (already shown this session)

    @app.post("/groups/{gid}/recs")
    def group_recs(gid: str, body: GroupRecsReq, user: str = Depends(current_user)):
        """One list per member from their own x, plus one from the group's average x."""
        g = _group(gid, user)
        if not g["members"]:
            raise HTTPException(409, "no members yet")
        cat = state["catalog"]
        exclude = {cat.id_to_idx[m] for m in body.exclude if m in cat.id_to_idx}
        users = {}
        for uid, f in g["members"].items():
            v, users[uid] = _recs(f, body.boost, exclude)
        v, model = state["trainer"].current()
        s = boost(score_feed(model, g["avg_x"], cat.vecs), cat.movies, body.boost)
        group = [{"rec_id": None, **cat.public(it["idx"]), "score": float(s[it["idx"]]), "because_of": []}
                 for it in pick(s, exclude=exclude)]  # not logged: there is no feed to log it under
        return {"group_id": gid, "w_version": v, "users": users, "group": group}

    class Feedback(BaseModel):
        rec_id: int | None = None
        feed_id: str | None = None
        movie_id: int | None = None    # catalog movie id, for feedback outside a rec list (e.g. a group vote)
        label: Literal["love", "seen_loved", "nah"]

    @app.post("/feedback")
    def feedback(body: Feedback, user: str = Depends(current_user)):
        """Group votes: yes -> love, no -> nah. Without feed_id it goes on the caller's latest feed."""
        store, cat = state["store"], state["catalog"]
        v, _ = state["trainer"].current()
        if body.rec_id is not None:
            rec = store.get_rec(body.rec_id)
            if not rec:
                raise HTTPException(404, "unknown rec_id")
            _feed(rec["feed_id"], user)
            fid, idx, v = rec["feed_id"], rec["movie_idx"], rec["w_version"]
        else:
            if body.movie_id not in cat.id_to_idx:
                raise HTTPException(400, "send rec_id, or a known movie_id")
            if body.feed_id is not None:
                fid = _feed(body.feed_id, user)["id"]
            else:
                f = store.latest_feed(user)
                if not f:
                    raise HTTPException(409, "upload a feed first")
                fid = f["id"]
            idx = cat.id_to_idx[body.movie_id]
        store.add_event(fid, idx, body.label, v, rec_id=body.rec_id)
        state["trainer"].notify_event()
        return {"ok": True, "events": store.count_events()}

    @app.post("/admin/retrain", dependencies=[Depends(require_admin)])
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


app = create_app()
