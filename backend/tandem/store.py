"""SQLite log: feeds, what we showed, what people tapped, and every W version we trained."""
import json
import sqlite3
import threading
import time
import uuid

import numpy as np

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS feeds (
  id TEXT PRIMARY KEY, user TEXT, created REAL, tags TEXT, x BLOB
);
CREATE TABLE IF NOT EXISTS recs (
  id INTEGER PRIMARY KEY, feed_id TEXT, movie_idx INT, rank INT, explore INT, w_version INT, created REAL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, feed_id TEXT, movie_idx INT, label TEXT, rec_id INT,
  split TEXT DEFAULT 'train', w_version INT, created REAL
);
CREATE TABLE IF NOT EXISTS models (
  version INT PRIMARY KEY, created REAL, path TEXT, accepted INT,
  recall_new REAL, recall_old REAL, n_train INT, n_holdout INT, n_events INT, loss REAL
);
"""


class Store:
    def __init__(self, path=None):
        path = path or config.DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # feeds
    def add_feed(self, user, tags, x):
        """tags: {ig_tag: weight} as the vision model read them; x: the IG vector built from them."""
        fid = uuid.uuid4().hex[:12]
        self._exec("INSERT INTO feeds VALUES (?,?,?,?,?)",
                   (fid, user, time.time(), json.dumps(tags), x.astype(np.float32).tobytes()))
        return fid

    def get_feed(self, fid):
        rows = self._all("SELECT * FROM feeds WHERE id=?", (fid,))
        if not rows:
            return None
        r = rows[0]
        r["tags"] = json.loads(r["tags"])
        r["x"] = np.frombuffer(r["x"], dtype=np.float32)
        return r

    def all_feed_vectors(self):
        rows = self._all("SELECT id, x FROM feeds")
        return {r["id"]: np.frombuffer(r["x"], dtype=np.float32) for r in rows}

    # recs + events
    def add_recs(self, fid, items, w_version):
        now = time.time()
        ids = []
        for it in items:
            cur = self._exec("INSERT INTO recs (feed_id, movie_idx, rank, explore, w_version, created) VALUES (?,?,?,?,?,?)",
                             (fid, it["idx"], it["rank"], int(it["explore"]), w_version, now))
            ids.append(cur.lastrowid)
        return ids

    def get_rec(self, rec_id):
        rows = self._all("SELECT * FROM recs WHERE id=?", (rec_id,))
        return rows[0] if rows else None

    def add_event(self, fid, movie_idx, label, w_version, rec_id=None, split="train"):
        # One label per (feed, movie): a later tap replaces an earlier one.
        self._exec("DELETE FROM events WHERE feed_id=? AND movie_idx=?", (fid, movie_idx))
        self._exec("INSERT INTO events (feed_id, movie_idx, label, rec_id, split, w_version, created) VALUES (?,?,?,?,?,?,?)",
                   (fid, movie_idx, label, rec_id, split, w_version, time.time()))

    def events(self):
        return self._all("SELECT * FROM events ORDER BY created, id")

    def rated_movies(self, fid):
        return {r["movie_idx"] for r in self._all("SELECT movie_idx FROM events WHERE feed_id=?", (fid,))}

    def count_events(self):
        return self._all("SELECT COUNT(*) AS n FROM events")[0]["n"]

    # models
    def add_model(self, **row):
        cols = ",".join(row)
        self._exec(f"INSERT INTO models ({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))

    def models(self):
        return self._all("SELECT * FROM models ORDER BY version")

    def latest_accepted(self):
        rows = self._all("SELECT * FROM models WHERE accepted=1 ORDER BY version DESC LIMIT 1")
        return rows[0] if rows else None
