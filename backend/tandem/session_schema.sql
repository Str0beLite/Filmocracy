-- Additive SQLite session schema; main's feeds/recs/events/models stay unchanged.
CREATE TABLE IF NOT EXISTS tandem_schema_versions(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS tandem_profiles (
  id TEXT PRIMARY KEY, display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 60)
);
CREATE TABLE IF NOT EXISTS tandem_movies (
  id INTEGER PRIMARY KEY, tmdb_id INTEGER UNIQUE, title TEXT NOT NULL, year INTEGER,
  tags TEXT NOT NULL, vector_index INTEGER NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS tandem_movie_metadata (
  provider TEXT NOT NULL, provider_movie_id TEXT NOT NULL, source_id INTEGER,
  catalog_movie_id INTEGER UNIQUE REFERENCES tandem_movies(id), details TEXT NOT NULL,
  PRIMARY KEY(provider,provider_movie_id)
);
CREATE TABLE IF NOT EXISTS tandem_sessions (
  id TEXT PRIMARY KEY, host_user_id TEXT NOT NULL REFERENCES tandem_profiles(id),
  status TEXT NOT NULL DEFAULT 'lobby' CHECK(status IN ('lobby','active','ended')),
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, ended_at TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  CHECK((status='ended')=(ended_at IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS tandem_members (
  session_id TEXT NOT NULL REFERENCES tandem_sessions(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES tandem_profiles(id), is_voter INTEGER NOT NULL CHECK(is_voter IN (0,1)),
  joined_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, left_at TEXT,
  PRIMARY KEY(session_id,user_id)
);
CREATE TABLE IF NOT EXISTS tandem_invites (
  session_id TEXT PRIMARY KEY REFERENCES tandem_sessions(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE CHECK(length(token_hash)=64), expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tandem_queue (
  session_id TEXT NOT NULL REFERENCES tandem_sessions(id) ON DELETE CASCADE,
  movie_id INTEGER NOT NULL REFERENCES tandem_movies(id), position INTEGER NOT NULL CHECK(position>0), shown_at TEXT,
  PRIMARY KEY(session_id,movie_id), UNIQUE(session_id,position)
);
CREATE TABLE IF NOT EXISTS tandem_rounds (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, movie_id INTEGER NOT NULL,
  opened_at TEXT NOT NULL, closed_at TEXT,
  close_reason TEXT CHECK(close_reason IN ('completed','skipped','ended')),
  UNIQUE(session_id,movie_id), UNIQUE(session_id,id),
  FOREIGN KEY(session_id,movie_id) REFERENCES tandem_queue(session_id,movie_id),
  CHECK((closed_at IS NULL)=(close_reason IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS tandem_one_open_round ON tandem_rounds(session_id) WHERE closed_at IS NULL;
CREATE TABLE IF NOT EXISTS tandem_electorate (
  session_id TEXT NOT NULL, round_id TEXT NOT NULL REFERENCES tandem_rounds(id),
  user_id TEXT NOT NULL, excluded_at TEXT,
  PRIMARY KEY(round_id,user_id), UNIQUE(session_id,round_id,user_id),
  FOREIGN KEY(session_id,round_id) REFERENCES tandem_rounds(session_id,id),
  FOREIGN KEY(session_id,user_id) REFERENCES tandem_members(session_id,user_id)
);
CREATE TABLE IF NOT EXISTS tandem_votes (
  session_id TEXT NOT NULL, round_id TEXT NOT NULL, user_id TEXT NOT NULL,
  value INTEGER NOT NULL CHECK(value IN (-1,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(round_id,user_id),
  FOREIGN KEY(session_id,round_id,user_id) REFERENCES tandem_electorate(session_id,round_id,user_id),
  FOREIGN KEY(session_id,user_id) REFERENCES tandem_members(session_id,user_id)
);
CREATE TABLE IF NOT EXISTS session_feeds (
  session_id TEXT, user_id TEXT, feed_id TEXT, PRIMARY KEY(session_id,user_id)
);
CREATE TABLE IF NOT EXISTS session_predictions(session_id TEXT PRIMARY KEY,scores TEXT);
CREATE TABLE IF NOT EXISTS vote_sync (
  session_id TEXT, round_id TEXT, user_id TEXT, value INTEGER, PRIMARY KEY(session_id,round_id,user_id)
);
INSERT OR IGNORE INTO tandem_schema_versions VALUES (1);

INSERT OR IGNORE INTO tandem_schema_versions VALUES (2);
-- Additive guards also protect databases initialized before the catalog table existed.
CREATE TRIGGER IF NOT EXISTS tandem_queue_movie_insert BEFORE INSERT ON tandem_queue
WHEN NOT EXISTS(SELECT 1 FROM tandem_movies WHERE id=NEW.movie_id)
BEGIN SELECT RAISE(ABORT,'Unknown catalog movie'); END;
CREATE TRIGGER IF NOT EXISTS tandem_queue_movie_update BEFORE UPDATE OF movie_id ON tandem_queue
WHEN NOT EXISTS(SELECT 1 FROM tandem_movies WHERE id=NEW.movie_id)
BEGIN SELECT RAISE(ABORT,'Unknown catalog movie'); END;
