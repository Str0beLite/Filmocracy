"""Session adapter; catalog IDs and group policy stay outside the model."""

import asyncio
import logging
import os
import re
import time
from urllib.parse import parse_qs, urlparse

import numpy as np
from fastapi import HTTPException
from tandem import config
from tandem.recommend import boost, pick, score_feed

log = logging.getLogger(__name__)

# Catalog tags each phone feeling boosts. Keep in step with FEELINGS in frontend/src/api/data.ts.
FEELING_BOOST = {
    "laugh": ["comedy", "funny", "hilarious"],
    "edge": ["suspense", "tense", "thriller"],
    "feels": ["emotional", "touching", "sad"],
    "mindblown": ["mindfuck", "twist ending", "cerebral"],
    "cozy": ["feel-good", "heartwarming"],
    "hyped": ["action", "action packed", "intense"],
}


def mean_scores(scores):
    return np.mean(scores, axis=0)


def movie_mapping(catalog, rows):
    by_tmdb = {}
    for idx, movie in enumerate(catalog.movies):
        key = str(movie.get("tmdb_id"))
        by_tmdb.setdefault(key, []).append(idx)
    result = {}
    for row in rows:
        matches = by_tmdb.get(str(row["provider_movie_id"]), [])
        if row["provider"] == "tmdb" and len(matches) == 1:
            result[row.get("id", row.get("source_id"))] = matches[0]
    return result


def youtube_id(row):
    if (row.get("trailer_provider") or "").lower() != "youtube":
        return None
    url = urlparse(row.get("trailer_url") or "")
    if url.scheme != "https":
        return None
    if url.hostname in ("youtube.com", "www.youtube.com"):
        value = parse_qs(url.query).get("v", [""])[0]
    elif url.hostname == "youtu.be":
        value = url.path.strip("/")
    else:
        return None
    return value if re.fullmatch(r"[A-Za-z0-9_-]{11}", value) else None


async def verify_trailer(client, row):
    vid = youtube_id(row)
    if not vid:
        return False
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        # shortcut: without a key we trust the catalog's YouTube id; set YOUTUBE_API_KEY to drop blocked/private trailers.
        return True
    response = await client.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"key": key, "id": vid, "part": "status,contentDetails"},
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    region = os.getenv("TRAILER_REGION", "US").upper()
    ok = False
    if items:
        item = items[0]
        status = item.get("status", {})
        restrictions = item.get("contentDetails", {}).get("regionRestriction", {})
        ok = (
            status.get("embeddable") is True
            and status.get("privacyStatus") == "public"
            and region not in restrictions.get("blocked", [])
            and ("allowed" not in restrictions or region in restrictions["allowed"])
            and not item.get("contentDetails", {}).get("contentRating", {}).get("ytRating")
        )
    return ok


def final_ranking(rounds, participants, votes, predictions):
    out = []
    for rnd in rounds:
        if rnd.get("close_reason") != "completed":
            continue
        electorate = {
            p["user_id"]
            for p in participants
            if p["round_id"] == rnd["id"] and not p.get("excluded_at")
        }
        values = {v["user_id"]: v["value"] for v in votes if v["round_id"] == rnd["id"]}
        yes = sum(v == 1 for v in values.values())
        unanimous = bool(values) and yes == len(values) and electorate <= values.keys()
        out.append(
            {
                "movie_id": rnd["movie_id"],
                "unanimous": unanimous,
                "likes": yes,
                "dislikes": sum(v == -1 for v in values.values()),
                "predicted_score": predictions.get(str(rnd["movie_id"]), 0.0),
            }
        )
    return sorted(
        out,
        key=lambda m: (
            -m["unanimous"],
            -m["likes"],
            m["dislikes"],
            -m["predicted_score"],
            m["movie_id"],
        ),
    )


class SessionRecommendations:
    def __init__(self, sessions, state, client, aggregate=mean_scores):
        self.sessions, self.state, self.client = sessions, state, client
        self.store = state["store"]
        self.aggregate = aggregate
        self.trailers = {}
        self.lock = asyncio.Lock()

    async def playable(self, row):
        vid = youtube_id(row)
        if not vid:
            return False
        region = os.getenv("TRAILER_REGION", "US").upper()
        key = (vid, region)
        cached = self.trailers.get(key)
        if cached and time.time() - cached[0] < 3600:
            return cached[1]
        ok = await verify_trailer(self.client, row)
        self.trailers[key] = time.time(), ok
        return ok

    def sync_votes(self):
        """Copy new session votes into the feedback log (and wake the trainer for each)."""
        version, _ = self.state["trainer"].current()
        synced = self.sessions.sync_feedback(version)
        for _ in range(synced):
            self.state["trainer"].notify_event()
        return synced

    def scores(self, feeds):
        """feeds: [(feed, feeling)]. Each voter's taste is pulled toward their yes votes and away from their no
        votes, then gets their own mood boost before averaging: a film that fits half the room's mood gets half."""
        _, model = self.state["trainer"].current()
        cat = self.state["catalog"]
        return self.aggregate(
            [
                boost(
                    score_feed(model, f["x"], cat.vecs, cat.prior, *self.store.votes(f["id"])),
                    cat.movies,
                    FEELING_BOOST.get(feeling, []),
                )
                for f, feeling in feeds
            ]
        )

    async def queue(self, sid, user):
        async with self.lock:
            try:
                seated, shown = await asyncio.to_thread(self.sessions.context, sid, user)
                feeds = [(self.store.get_feed(fid), feeling) for fid, feeling in seated]
                feeds = [(feed, feeling) for feed, feeling in feeds if feed]
                if not feeds:
                    raise HTTPException(409, "At least one connected voter needs a feed")
                candidates = [row for row in self.sessions.metadata() if row["id"] not in shown]
                semaphore = asyncio.Semaphore(6)

                async def check(row):
                    async with semaphore:
                        return await self.playable(row)

                tasks = [asyncio.create_task(check(row)) for row in candidates]
                try:
                    available = await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                cat = self.state["catalog"]
                eligible = {
                    cat.id_to_idx[row["id"]]: row["id"]
                    for row, ok in zip(candidates, available)
                    if ok
                }
                if not eligible:
                    raise HTTPException(
                        409, "No unshown, verified playable catalog matches available"
                    )
                await asyncio.to_thread(self.sync_votes)  # this round's votes steer the next films
                scores = await asyncio.to_thread(self.scores, feeds)
                if not np.isfinite(scores).all():
                    raise ValueError("Non-finite recommendation scores")
                items = pick(scores, exclude=set(range(len(scores))) - eligible.keys())[: config.SESSION_BATCH]
                predictions = {str(eligible[idx]): float(scores[idx]) for idx in eligible}
                return await asyncio.to_thread(
                    self.sessions.enqueue,
                    sid,
                    user,
                    [eligible[item["idx"]] for item in items],
                    predictions,
                )
            except HTTPException:
                raise
            except Exception:
                log.warning("Recommendation preparation failed; queue can be retried")
                raise HTTPException(
                    503, "Recommendations unavailable; retry queue or host skip/end"
                )

    async def training_next(self, fid, user, boost_tags):
        # Use the existing scorer and feedback format; a training visit is not a TV session.
        async with self.lock:
            feed = await asyncio.to_thread(self.store.get_feed, fid)
            if not feed:
                raise HTTPException(404, "Unknown feed")
            if feed["user"] != user:
                raise HTTPException(403, "This taste profile belongs to another user")
            shown = await asyncio.to_thread(
                self.store._all, "SELECT movie_idx FROM recs WHERE feed_id=?", (fid,)
            )
            excluded = {r["movie_idx"] for r in shown}
            excluded |= await asyncio.to_thread(self.store.rated_movies, fid)
            cat = self.state["catalog"]
            version, model = self.state["trainer"].current()
            votes = await asyncio.to_thread(self.store.votes, fid)
            scores = await asyncio.to_thread(
                score_feed, model, feed["x"], cat.vecs, cat.prior, *votes
            )
            scores = boost(scores, cat.movies, boost_tags)
            if not np.isfinite(scores).all():
                raise HTTPException(503, "Recommendations unavailable; try again")
            rows = {r["id"]: r for r in await asyncio.to_thread(self.sessions.metadata)}
            for idx in np.argsort(-scores):
                idx = int(idx)
                row = rows.get(cat.movies[idx]["id"])
                if idx in excluded or row is None:
                    continue
                try:
                    if not await self.playable(row):
                        continue
                except HTTPException:
                    raise
                except Exception:
                    raise HTTPException(503, "Trailer checks unavailable; try again")
                ids = await asyncio.to_thread(
                    self.store.add_recs, fid, [{"idx": idx, "rank": 1, "explore": False}], version
                )
                return {
                    "rec_id": ids[0],
                    "score": float(scores[idx]),
                    "w_version": version,
                    "movie": {**row, **cat.public(idx), "trailer_key": youtube_id(row)},
                }
            raise HTTPException(409, "You have watched all available verified trailers")

    async def rankings(self, sid, user):
        state = await asyncio.to_thread(self.sessions.snapshot, sid, user)
        predictions = await asyncio.to_thread(self.sessions.predictions, sid, user)
        return final_ranking(
            state["voting_rounds"], state["round_participants"], state["votes"], predictions
        )
