"""Session transactions over main's SQLite connection. No Supabase client or writes."""

import hashlib
import json
import secrets
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException


STAGE_MAX_BYTES = 16384
REACTION_SECONDS = 8   # reactions older than this drop out of snapshots


class SessionStore:
    def __init__(self, store, catalog, metadata, clock=time.time):
        self.store, self.catalog, self.clock = store, catalog, clock
        self.db = store.db
        with store.lock:
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA busy_timeout=5000")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript((Path(__file__).parent / "tandem/session_schema.sql").read_text())
        by_tmdb = {}
        for movie in catalog.movies:
            by_tmdb.setdefault(str(movie.get("tmdb_id")), []).append(movie["id"])
        with self.transaction() as db:
            for idx, movie in enumerate(catalog.movies):
                db.execute(
                    "INSERT INTO tandem_movies VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET title=excluded.title",  # catalog title fixes reach old databases
                    (
                        movie["id"],
                        movie.get("tmdb_id"),
                        movie["title"],
                        movie.get("year"),
                        json.dumps(movie.get("tags", {})),
                        idx,
                    ),
                )
            existing = {
                r["id"]: r["vector_index"]
                for r in db.execute("SELECT id,vector_index FROM tandem_movies")
            }
            if existing != catalog.id_to_idx:
                raise RuntimeError(
                    "SQLite movie IDs/order differ from model catalog; explicit migration required"
                )
            for row in metadata:
                matches = by_tmdb.get(str(row["provider_movie_id"]), [])
                mid = matches[0] if row["provider"] == "tmdb" and len(matches) == 1 else None
                db.execute(
                    "INSERT OR IGNORE INTO tandem_movie_metadata VALUES (?,?,?,?,?)",
                    (
                        row["provider"],
                        str(row["provider_movie_id"]),
                        row.get("source_id"),
                        mid,
                        json.dumps(row),
                    ),
                )

    @contextmanager
    def transaction(self, write=True):
        with self.store.lock:
            self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def stamp(self, offset=0):
        return datetime.fromtimestamp(self.clock() + offset, timezone.utc).isoformat(
            timespec="microseconds"
        )

    @staticmethod
    def touch(db, sid):
        db.execute("UPDATE tandem_sessions SET revision=revision+1 WHERE id=?", (sid,))

    @staticmethod
    def current(db, sid):
        return db.execute(
            "SELECT * FROM tandem_rounds WHERE session_id=? AND closed_at IS NULL", (sid,)
        ).fetchone()

    def member(self, db, sid, user, host=False):
        row = db.execute(
            "SELECT s.* FROM tandem_sessions s JOIN tandem_members m ON m.session_id=s.id "
            "WHERE s.id=? AND m.user_id=? AND m.left_at IS NULL",
            (sid, user),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        if host and row["host_user_id"] != user:
            raise HTTPException(403, "Host authority required")
        return row

    def close(self, db, rnd, reason):
        db.execute(
            "UPDATE tandem_rounds SET closed_at=?,close_reason=? WHERE id=?",
            (self.stamp(), reason, rnd["id"]),
        )
        self.touch(db, rnd["session_id"])

    def open_next(self, db, sid):
        nxt = db.execute(
            "SELECT * FROM tandem_queue WHERE session_id=? AND shown_at "
            "IS NULL ORDER BY position LIMIT 1",
            (sid,),
        ).fetchone()
        if not nxt:
            db.execute("UPDATE tandem_sessions SET status='lobby' WHERE id=?", (sid,))
            self.touch(db, sid)
            return None
        rid, now = str(uuid4()), self.stamp()
        db.execute(
            "INSERT INTO tandem_rounds VALUES (?,?,?,?,NULL,NULL)", (rid, sid, nxt["movie_id"], now)
        )
        db.execute(
            "UPDATE tandem_queue SET shown_at=? WHERE session_id=? AND movie_id=?",
            (now, sid, nxt["movie_id"]),
        )
        db.execute(
            "INSERT INTO tandem_electorate SELECT session_id,?,user_id,NULL FROM tandem_members "
            "WHERE session_id=? AND is_voter=1 AND left_at IS NULL AND last_seen_at>?",
            (rid, sid, self.stamp(-45)),
        )
        db.execute("UPDATE tandem_sessions SET status='active' WHERE id=?", (sid,))
        self.touch(db, sid)
        return rid

    def check(self, db, sid):
        session = db.execute("SELECT * FROM tandem_sessions WHERE id=?", (sid,)).fetchone()
        rnd = self.current(db, sid)
        if session["status"] == "ended":
            return None
        if session["expires_at"] <= self.stamp():
            if rnd:
                self.close(db, rnd, "ended")
            db.execute(
                "UPDATE tandem_sessions SET status='ended',ended_at=? WHERE id=?",
                (self.stamp(), sid),
            )
            self.touch(db, sid)
            return None
        if not rnd:
            return None
        expired = db.execute(
            "UPDATE tandem_electorate SET excluded_at=? WHERE round_id=? AND excluded_at IS NULL "
            "AND user_id IN (SELECT user_id FROM tandem_members WHERE session_id=? AND "
            "(left_at IS NOT NULL OR last_seen_at<=?))",
            (self.stamp(), rnd["id"], sid, self.stamp(-45)),
        ).rowcount
        if expired:
            self.touch(db, sid)
        votes = db.execute(
            "SELECT COUNT(*) FROM tandem_votes WHERE round_id=?", (rnd["id"],)
        ).fetchone()[0]
        outstanding = db.execute(
            "SELECT COUNT(*) FROM tandem_electorate e WHERE round_id=? AND excluded_at IS NULL "
            "AND NOT EXISTS(SELECT 1 FROM tandem_votes v WHERE "
            "v.round_id=e.round_id AND v.user_id=e.user_id)",
            (rnd["id"],),
        ).fetchone()[0]
        if votes and not outstanding:
            self.close(db, rnd, "completed")
            return self.open_next(db, sid)
        return rnd["id"]

    def profile(self, db, user, name):
        db.execute(
            "INSERT INTO tandem_profiles VALUES (?,?) ON CONFLICT(id) DO "
            "UPDATE SET display_name=excluded.display_name",
            (user, name),
        )

    def rotate(self, db, sid):
        token = secrets.token_hex(32)
        db.execute(
            "INSERT OR REPLACE INTO tandem_invites VALUES (?,?,?)",
            (sid, hashlib.sha256(token.encode()).hexdigest(), self.stamp(21600)),
        )
        return token

    def create(self, user, name):
        sid, now = str(uuid4()), self.stamp()
        with self.transaction() as db:
            self.profile(db, user, name)
            db.execute(
                "INSERT INTO tandem_sessions VALUES (?,?,'lobby',?,?,NULL,1)",
                (sid, user, now, self.stamp(21600)),
            )
            db.execute("INSERT INTO tandem_members VALUES (?,?,0,?,?,NULL)", (sid, user, now, now))
            token = self.rotate(db, sid)
        return {"session_id": sid, "invite_token": token}

    def join(self, user, name, token):
        with self.transaction() as db:
            invite = db.execute(
                "SELECT * FROM tandem_invites WHERE token_hash=? AND expires_at>?",
                (hashlib.sha256(token.encode()).hexdigest(), self.stamp()),
            ).fetchone()
            if not invite:
                raise HTTPException(400, "Invitation invalid or expired")
            sid = invite["session_id"]
            self.check(db, sid)
            session = db.execute("SELECT * FROM tandem_sessions WHERE id=?", (sid,)).fetchone()
            if session["status"] == "ended":
                raise HTTPException(409, "Session has ended")
            self.profile(db, user, name)
            now = self.stamp()
            db.execute(
                "INSERT INTO tandem_members VALUES (?,?,?,?,?,NULL) ON "
                "CONFLICT(session_id,user_id) "
                "DO UPDATE SET last_seen_at=excluded.last_seen_at,left_at=NULL",
                (sid, user, int(user != session["host_user_id"]), now, now),
            )
            latest = db.execute(
                "SELECT id FROM feeds WHERE user=? ORDER BY created DESC LIMIT 1", (user,)
            ).fetchone()
            if latest:
                db.execute(
                    "INSERT OR IGNORE INTO session_feeds VALUES (?,?,?)", (sid, user, latest["id"])
                )
            self.touch(db, sid)
        return {"session_id": sid}

    def invitation(self, sid, user):
        with self.transaction() as db:
            self.member(db, sid, user, host=True)
            if (
                db.execute("SELECT status FROM tandem_sessions WHERE id=?", (sid,)).fetchone()[0]
                == "ended"
            ):
                raise HTTPException(409, "Session has ended")
            token = self.rotate(db, sid)
        return {"invite_token": token}

    def heartbeat(self, sid, user, leave=False):
        with self.transaction() as db:
            self.member(db, sid, user)
            self.check(db, sid)
            db.execute(
                "UPDATE tandem_members SET last_seen_at=?,left_at=? WHERE "
                "session_id=? AND user_id=?",
                (self.stamp(), self.stamp() if leave else None, sid, user),
            )
            self.touch(db, sid)
            rid = self.check(db, sid)
        return {"round_id": rid}

    def vote(self, sid, user, rid, value):
        if value not in (-1, 1):
            raise HTTPException(422, "Vote must be -1 or 1")
        with self.transaction() as db:
            self.member(db, sid, user)
            current = self.check(db, sid)
            if current != rid:
                return {"round_id": current}
            eligible = db.execute(
                "SELECT 1 FROM tandem_electorate WHERE round_id=? AND "
                "user_id=? AND excluded_at IS NULL",
                (rid, user),
            ).fetchone()
            if not eligible:
                raise HTTPException(403, "Not eligible for this round")
            now = self.stamp()
            db.execute(
                "UPDATE tandem_members SET last_seen_at=? WHERE session_id=? AND user_id=?",
                (now, sid, user),
            )
            db.execute(
                "INSERT INTO tandem_votes VALUES (?,?,?,?,?,?) ON CONFLICT(round_id,user_id) "
                "DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (sid, rid, user, value, now, now),
            )
            self.touch(db, sid)
            current = self.check(db, sid)
        return {"round_id": current}

    def control(self, sid, user, action, expected=None):
        with self.transaction() as db:
            session = self.member(db, sid, user, host=True)
            if session["status"] == "ended":
                return {"round_id": None}
            self.check(db, sid)
            rnd = self.current(db, sid)
            if action == "end":
                if rnd:
                    self.close(db, rnd, "ended")
                db.execute(
                    "UPDATE tandem_sessions SET status='ended',ended_at=? WHERE id=?",
                    (self.stamp(), sid),
                )
                self.touch(db, sid)
                return {"round_id": None}
            if (
                db.execute("SELECT status FROM tandem_sessions WHERE id=?", (sid,)).fetchone()[0]
                == "ended"
            ):
                return {"round_id": None}
            if action == "skip":
                if not expected:
                    raise HTTPException(422, "Skipping requires expected_round_id")
                if not rnd or rnd["id"] != expected:
                    return {"round_id": rnd["id"] if rnd else None}
                self.close(db, rnd, "skipped")
            elif action != "start":
                raise HTTPException(422, "Unknown action")
            elif rnd:
                return {"round_id": rnd["id"]}
            return {"round_id": self.open_next(db, sid)}

    def snapshot(self, sid, user):
        with self.transaction(write=False) as db:
            session = dict(self.member(db, sid, user))
            tables = {
                "session_members": "tandem_members",
                "session_movies": "tandem_queue",
                "voting_rounds": "tandem_rounds",
                "round_participants": "tandem_electorate",
                "votes": "tandem_votes",
            }
            out = {"session": session}
            for key, table in tables.items():
                out[key] = [
                    dict(row)
                    for row in db.execute(f"SELECT * FROM {table} WHERE session_id=?", (sid,))
                ]
            stage = db.execute("SELECT stage FROM tandem_stage WHERE session_id=?", (sid,)).fetchone()
            out["stage"] = json.loads(stage["stage"]) if stage else {}
            out["member_state"] = [
                dict(row)
                for row in db.execute(
                    "SELECT user_id,feeling FROM tandem_member_state WHERE session_id=?", (sid,)
                )
            ]
            out["session_feeds"] = [
                row["user_id"]
                for row in db.execute("SELECT user_id FROM session_feeds WHERE session_id=?", (sid,))
            ]
            out["reactions"] = [
                dict(row)
                for row in db.execute(
                    "SELECT id,user_id,emoji,created_at FROM tandem_reactions "
                    "WHERE session_id=? AND created_at>? ORDER BY id",
                    (sid, self.stamp(-REACTION_SECONDS)),
                )
            ]
            out["server_now"] = self.stamp()
            out["profiles"] = [
                dict(row)
                for row in db.execute(
                    "SELECT p.* FROM tandem_profiles p JOIN tandem_members m ON m.user_id=p.id "
                    "WHERE m.session_id=?",
                    (sid,),
                )
            ]
        return out

    def set_stage(self, sid, user, stage):
        """Host only: what the TV is showing, as JSON every member receives in the snapshot."""
        text = json.dumps(stage, separators=(",", ":"))
        if len(text) > STAGE_MAX_BYTES:
            raise HTTPException(413, "Stage too large")
        with self.transaction() as db:
            self.member(db, sid, user, host=True)
            db.execute(
                "INSERT INTO tandem_stage VALUES (?,?) ON CONFLICT(session_id) "
                "DO UPDATE SET stage=excluded.stage",
                (sid, text),
            )
            self.touch(db, sid)
        return {"ok": True}

    def set_feeling(self, sid, user, feeling):
        with self.transaction() as db:
            self.member(db, sid, user)
            db.execute(
                "INSERT INTO tandem_member_state VALUES (?,?,?) ON CONFLICT(session_id,user_id) "
                "DO UPDATE SET feeling=excluded.feeling",
                (sid, user, feeling),
            )
            self.touch(db, sid)
        return {"ok": True}

    def react(self, sid, user, emoji):
        with self.transaction() as db:
            self.member(db, sid, user)
            db.execute(
                "DELETE FROM tandem_reactions WHERE session_id=? AND created_at<=?",
                (sid, self.stamp(-REACTION_SECONDS)),
            )
            db.execute(
                "INSERT INTO tandem_reactions(session_id,user_id,emoji,created_at) VALUES (?,?,?,?)",
                (sid, user, emoji, self.stamp()),
            )
            self.touch(db, sid)
        return {"ok": True}

    def get_profile(self, user):
        with self.transaction(write=False) as db:
            row = db.execute("SELECT * FROM tandem_profiles WHERE id=?", (user,)).fetchone()
            return dict(row) if row else {"id": user, "display_name": None}

    def update_profile(self, user, name):
        with self.transaction() as db:
            self.profile(db, user, name)
            db.execute(
                "UPDATE tandem_sessions SET revision=revision+1 WHERE id IN "
                "(SELECT session_id FROM tandem_members WHERE user_id=?)",
                (user,),
            )
        return {"id": user, "display_name": name}

    def delete_account(self, user):
        """Drop a person's feeds, votes-as-training and name. Past nights keep an anonymous seat."""
        with self.transaction() as db:
            feeds = "SELECT id FROM feeds WHERE user=?"
            db.execute(f"DELETE FROM events WHERE feed_id IN ({feeds})", (user,))
            db.execute(f"DELETE FROM recs WHERE feed_id IN ({feeds})", (user,))
            db.execute("DELETE FROM feeds WHERE user=?", (user,))
            db.execute("DELETE FROM session_feeds WHERE user_id=?", (user,))
            if db.execute(
                "SELECT 1 FROM tandem_members WHERE user_id=? UNION SELECT 1 FROM tandem_sessions"
                " WHERE host_user_id=?",
                (user, user),
            ).fetchone():
                # Session rows reference the profile, so it stays, nameless.
                db.execute("UPDATE tandem_profiles SET display_name='Guest' WHERE id=?", (user,))
            else:
                db.execute("DELETE FROM tandem_profiles WHERE id=?", (user,))
        return {"ok": True}

    def bind(self, sid, user, fid):
        with self.transaction() as db:
            self.member(db, sid, user)
            if not db.execute("SELECT 1 FROM feeds WHERE id=? AND user=?", (fid, user)).fetchone():
                raise HTTPException(404, "Feed not found")
            bound = db.execute(
                "SELECT feed_id FROM session_feeds WHERE session_id=? AND user_id=?", (sid, user)
            ).fetchone()
            if bound and bound[0] != fid:
                raise HTTPException(409, "Session feed cannot be replaced")
            db.execute("INSERT OR IGNORE INTO session_feeds VALUES (?,?,?)", (sid, user, fid))
            self.touch(db, sid)
        return {"feed_id": fid}

    def context(self, sid, user):
        with self.transaction(write=False) as db:
            session = self.member(db, sid, user, host=True)
            if session["status"] == "ended":
                raise HTTPException(409, "Session has ended")
            feeds = [  # (feed_id, feeling or None) per connected voter
                (r[0], r[1])
                for r in db.execute(
                    "SELECT f.feed_id, s.feeling FROM session_feeds f JOIN tandem_members m "
                    "ON m.session_id=f.session_id AND m.user_id=f.user_id "
                    "LEFT JOIN tandem_member_state s ON s.session_id=f.session_id AND s.user_id=f.user_id "
                    "WHERE f.session_id=? AND m.is_voter=1 AND m.left_at IS NULL AND m.last_seen_at>?",
                    (sid, self.stamp(-45)),
                )
            ]
            shown = {  # unshown films are re-picked on every queue call
                r[0]
                for r in db.execute(
                    "SELECT movie_id FROM tandem_queue WHERE session_id=? AND shown_at IS NOT NULL",
                    (sid,),
                )
            }
        return feeds, shown

    def movies(self, offset=0, limit=100):
        with self.transaction(write=False) as db:
            total = db.execute("SELECT COUNT(*) FROM tandem_movies").fetchone()[0]
            rows = db.execute(
                "SELECT id,tmdb_id,title,year FROM tandem_movies "
                "ORDER BY vector_index LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "movies": [dict(row) for row in rows],
            }

    def save_metadata(self, movie_id, row):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO tandem_movie_metadata VALUES (?,?,?,?,?) "
                "ON CONFLICT(provider,provider_movie_id) DO UPDATE SET "
                "catalog_movie_id=excluded.catalog_movie_id,details=excluded.details",
                (row["provider"], row["provider_movie_id"], None, movie_id, json.dumps(row)),
            )

    def metadata(self):
        with self.transaction(write=False) as db:
            return [
                {**json.loads(r["details"]), "id": r["catalog_movie_id"]}
                for r in db.execute(
                    "SELECT * FROM tandem_movie_metadata WHERE catalog_movie_id IS NOT NULL"
                )
            ]

    def enqueue(self, sid, user, ids, predictions):
        with self.transaction() as db:
            session = self.member(db, sid, user, host=True)
            if session["status"] == "ended":
                raise HTTPException(409, "Session has ended")
            # Replace what hasn't been shown yet, so the latest votes decide what comes next.
            db.execute("DELETE FROM tandem_queue WHERE session_id=? AND shown_at IS NULL", (sid,))
            pos = db.execute(
                "SELECT COALESCE(MAX(position),0) FROM tandem_queue WHERE session_id=?", (sid,)
            ).fetchone()[0]
            count = 0
            for mid in ids:
                if mid not in self.catalog.id_to_idx:
                    raise HTTPException(400, "Unknown catalog movie")
                if db.execute(
                    "SELECT 1 FROM tandem_queue WHERE session_id=? AND movie_id=?", (sid, mid)
                ).fetchone():
                    continue
                pos += 1
                count += 1
                db.execute("INSERT INTO tandem_queue VALUES (?,?,?,NULL)", (sid, mid, pos))
            row = db.execute(
                "SELECT scores FROM session_predictions WHERE session_id=?", (sid,)
            ).fetchone()
            scores = json.loads(row[0]) if row else {}
            scores.update(predictions)
            db.execute(
                "INSERT OR REPLACE INTO session_predictions VALUES (?,?)", (sid, json.dumps(scores))
            )
            self.touch(db, sid)
        return {"added": count}

    def predictions(self, sid, user):
        with self.transaction(write=False) as db:
            self.member(db, sid, user)
            row = db.execute(
                "SELECT scores FROM session_predictions WHERE session_id=?", (sid,)
            ).fetchone()
            return json.loads(row[0]) if row else {}

    def sweep(self):
        with self.transaction() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM tandem_sessions WHERE status<>'ended'")]
            for sid in ids:
                self.check(db, sid)

    def sync_feedback(self, version):
        # Separate from accepted-vote transactions: a failure here can never undo a vote.
        with self.transaction() as db:
            rows = db.execute(
                "SELECT v.*,f.feed_id,r.movie_id FROM tandem_votes v "
                "JOIN tandem_rounds r ON r.id=v.round_id JOIN session_feeds f"
                " ON f.session_id=v.session_id AND f.user_id=v.user_id "
                "LEFT JOIN vote_sync s ON s.session_id=v.session_id AND "
                "s.round_id=v.round_id AND s.user_id=v.user_id "
                "WHERE s.value IS NULL OR s.value<>v.value"
            ).fetchall()
            for row in rows:
                idx = self.catalog.id_to_idx.get(row["movie_id"])
                if idx is None:
                    continue
                db.execute(
                    "DELETE FROM events WHERE feed_id=? AND movie_idx=?", (row["feed_id"], idx)
                )
                db.execute(
                    "INSERT INTO "
                    "events(feed_id,movie_idx,label,split,w_version,created) "
                    "VALUES (?,?,?,'train',?,?)",
                    (
                        row["feed_id"],
                        idx,
                        "love" if row["value"] == 1 else "nah",
                        version,
                        self.clock(),
                    ),
                )
                db.execute(
                    "INSERT OR REPLACE INTO vote_sync VALUES (?,?,?,?)",
                    (row["session_id"], row["round_id"], row["user_id"], row["value"]),
                )
        return len(rows)
