"""Session adapter; catalog IDs and group policy stay outside the model."""

import asyncio
import logging
import os
import re
import time
from urllib.parse import parse_qs, urlparse

import numpy as np
from fastapi import HTTPException
from tandem.recommend import pick, score_feed

log = logging.getLogger(__name__)


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

    def scores(self, feeds):
        _, model = self.state["trainer"].current()
        return self.aggregate(
            [score_feed(model, f["x"], self.state["catalog"].vecs) for f in feeds]
        )

    async def queue(self, sid, user):
        async with self.lock:
            try:
                feed_ids, queued = await asyncio.to_thread(self.sessions.context, sid, user)
                feeds = [self.store.get_feed(fid) for fid in feed_ids]
                feeds = [feed for feed in feeds if feed]
                if not feeds:
                    raise HTTPException(409, "At least one connected voter needs a feed")
                candidates = [row for row in self.sessions.metadata() if row["id"] not in queued]
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
                scores = await asyncio.to_thread(self.scores, feeds)
                if not np.isfinite(scores).all():
                    raise ValueError("Non-finite recommendation scores")
                items = pick(scores, exclude=set(range(len(scores))) - eligible.keys())
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

    async def rankings(self, sid, user):
        state = await asyncio.to_thread(self.sessions.snapshot, sid, user)
        predictions = await asyncio.to_thread(self.sessions.predictions, sid, user)
        return final_ranking(
            state["voting_rounds"], state["round_participants"], state["votes"], predictions
        )
