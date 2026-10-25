"""Session adapter; catalog IDs and group policy stay outside the model."""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
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
            result[row["id"]] = matches[0]
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
        raise HTTPException(503, "Trailer verification requires YOUTUBE_API_KEY")
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
    def __init__(self, db, state, aggregate=mean_scores):
        self.db, self.state, self.aggregate = db, state, aggregate
        self.store = state["store"]
        self.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS session_feeds (
              session_id TEXT, user_id TEXT, feed_id TEXT,
              PRIMARY KEY(session_id,user_id));
            CREATE TABLE IF NOT EXISTS session_predictions (
              session_id TEXT PRIMARY KEY, scores TEXT);
            CREATE TABLE IF NOT EXISTS vote_sync (
              session_id TEXT, round_id TEXT, user_id TEXT, value INT,
              PRIMARY KEY(session_id,round_id,user_id));
        """)
        self.trailers = {}
        self.lock = asyncio.Lock()

    async def rows(self, table, sid=None, token=None):
        params = {"select": "*"}
        if sid:
            params["id" if table == "group_sessions" else "session_id"] = f"eq.{sid}"
        return await self.db.request(
            "GET", f"/rest/v1/{table}", params=params, token=token, privileged=token is None
        )

    async def member(self, sid, token):
        rows = await self.rows("group_sessions", sid, token)
        if not rows:
            raise HTTPException(404, "Session not found")
        return rows[0]

    async def bind(self, sid, fid, user, token):
        await self.member(sid, token)
        feed = self.store.get_feed(fid)
        if not feed or feed["user"] != user:
            raise HTTPException(404, "Feed not found")
        existing = self.store._all(
            "SELECT * FROM session_feeds WHERE session_id=? AND user_id=?", (sid, user)
        )
        if existing and existing[0]["feed_id"] != fid:
            raise HTTPException(409, "Session feed cannot be replaced; create a new session")
        self.store._exec("INSERT OR IGNORE INTO session_feeds VALUES (?,?,?)", (sid, user, fid))
        return {"feed_id": fid}

    async def playable(self, row):
        vid = youtube_id(row)
        if not vid:
            return False
        cached = self.trailers.get(vid)
        if cached and time.time() - cached[0] < 3600:
            return cached[1]
        ok = await verify_trailer(self.db.client, row)
        self.trailers[vid] = time.time(), ok
        return ok

    def scores(self, feeds):
        _, model = self.state["trainer"].current()
        return self.aggregate(
            [score_feed(model, f["x"], self.state["catalog"].vecs) for f in feeds]
        )

    async def queue(self, sid, token):
        async with self.lock:
            session = await self.member(sid, token)
            user = await self.db.request("GET", "/auth/v1/user", token=token)
            if session["host_user_id"] != user["id"]:
                raise HTTPException(403, "Only the host can prepare the queue")
            if session["status"] == "ended":
                raise HTTPException(409, "Session has ended")
            members = await self.rows("session_members", sid, token)
            now = datetime.now(timezone.utc)
            active = {
                m["user_id"]
                for m in members
                if not m.get("left_at")
                and m["is_voter"]
                and (
                    not m.get("last_seen_at")
                    or (
                        now - datetime.fromisoformat(m["last_seen_at"].replace("Z", "+00:00"))
                    ).total_seconds()
                    < 45
                )
            }
            bindings = self.store._all("SELECT * FROM session_feeds WHERE session_id=?", (sid,))
            feeds = [self.store.get_feed(b["feed_id"]) for b in bindings if b["user_id"] in active]
            if not feeds:
                raise HTTPException(
                    409, "Attach at least one participant feed before preparing queue"
                )
            try:
                catalog = await self.rows("movies", token=token)
                mapping = movie_mapping(self.state["catalog"], catalog)
                queued = {m["movie_id"] for m in await self.rows("session_movies", sid, token)}
                candidates = [r for r in catalog if r["id"] in mapping and r["id"] not in queued]
                semaphore = asyncio.Semaphore(6)

                async def check(row):
                    async with semaphore:
                        return await self.playable(row)

                available = await asyncio.gather(*(check(row) for row in candidates))
                eligible = {
                    mapping[row["id"]]: row["id"] for row, ok in zip(candidates, available) if ok
                }
                if not eligible:
                    raise HTTPException(
                        409, "No unshown, verified playable catalog matches available"
                    )
                scores = await asyncio.to_thread(self.scores, feeds)
                if not np.isfinite(scores).all():
                    raise ValueError("Non-finite recommendation scores")
                selected = pick(scores, exclude=set(range(len(scores))) - eligible.keys())
                predictions = self.store._all(
                    "SELECT scores FROM session_predictions WHERE session_id=?", (sid,)
                )
                saved = json.loads(predictions[0]["scores"]) if predictions else {}
                saved.update({str(eligible[i]): float(scores[i]) for i in eligible})
                self.store._exec(
                    "INSERT OR REPLACE INTO session_predictions VALUES (?,?)",
                    (sid, json.dumps(saved)),
                )
                count = await self.db.rpc(
                    "enqueue_movies",
                    {"p_session": sid, "p_movies": [eligible[item["idx"]] for item in selected]},
                    token=token,
                )
                return {"added": count}
            except HTTPException:
                raise
            except Exception:
                log.warning("Recommendation preparation failed; queue can be retried")
                raise HTTPException(
                    503, "Recommendations unavailable; retry queue or host skip/end"
                )

    async def reconcile(self):
        # Supabase remains authoritative, including votes written directly through its RPC.
        async with self.lock:
            bindings = self.store._all("SELECT * FROM session_feeds")
            for sid in {b["session_id"] for b in bindings}:
                mapping = movie_mapping(self.state["catalog"], await self.rows("movies"))
                rounds = {r["id"]: r for r in await self.rows("voting_rounds", sid)}
                for vote in await self.rows("votes", sid):
                    binding = next(
                        (
                            b
                            for b in bindings
                            if b["session_id"] == sid and b["user_id"] == vote["user_id"]
                        ),
                        None,
                    )
                    rnd = rounds.get(vote["round_id"])
                    if not binding or not rnd or rnd["movie_id"] not in mapping:
                        continue
                    args = (sid, vote["round_id"], vote["user_id"])
                    synced = self.store._all(
                        "SELECT value FROM vote_sync "
                        "WHERE session_id=? AND round_id=? AND user_id=?",
                        args,
                    )
                    if synced and synced[0]["value"] == vote["value"]:
                        continue
                    version, _ = self.state["trainer"].current()
                    self.store.add_event(
                        binding["feed_id"],
                        mapping[rnd["movie_id"]],
                        "love" if vote["value"] == 1 else "nah",
                        version,
                    )
                    self.store._exec(
                        "INSERT OR REPLACE INTO vote_sync VALUES (?,?,?,?)", (*args, vote["value"])
                    )

    async def rankings(self, sid, token):
        await self.member(sid, token)
        rows = self.store._all("SELECT scores FROM session_predictions WHERE session_id=?", (sid,))
        return final_ranking(
            await self.rows("voting_rounds", sid, token),
            await self.rows("round_participants", sid, token),
            await self.rows("votes", sid, token),
            json.loads(rows[0]["scores"]) if rows else {},
        )
