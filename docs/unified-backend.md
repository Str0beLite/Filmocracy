# Unified SQLite backend

The feature branch retains all recommendation features from main and moves the entire
active session backend to **main's SQLite database**. Supabase is no longer a runtime
dependency. Its remote database and applied migration history remain unchanged.

## Run

From the repository root, install PyTorch and `backend/requirements.txt`, export your
server variables, then run one command:

```bash
backend/.venv/bin/uvicorn unified:app --app-dir backend --host 0.0.0.0 --port 8000
```

`app:app` forwards to this same application. Docker and Railway use `unified:app`.
Required: `GOOGLE_CLIENT_ID`. Optional for screenshots: `LLAMA_API_KEY`,
`LLAMA_BASE_URL`, `LLAMA_MODEL`. Queue preparation requires `YOUTUBE_API_KEY`;
`TRAILER_REGION` defaults to US. Set `FRONTEND_ORIGINS` to exact comma-separated
frontend origins. `TANDEM_DATA_DIR` contains `tandem.db` and checkpoints; the movie
vectors/catalog remain under `TANDEM_CATALOG_DIR` (default `backend/catalog`).
No Supabase URL, key, JWT, SDK, or Realtime subscription is needed.

All user routes use main's `Authorization: Bearer <Google ID token>` and Google `sub`
as the user ID. `TANDEM_DEV_AUTH=1` supports main's local development identity shortcut;
it must never be used in production, and unified refuses it on Railway. For deployment,
use Google's configured web client and refresh sign-in tokens through the frontend.
Tokens are not stored in SQLite or localStorage by our TV helper.

## What stays from main

The existing model, checkpoints, encoder, scoring, exploration, tag boosting, SQLite
feeds/recs/events/models schema, latest-feed behavior, Google auth and tests are kept.
All `/me`, `/feeds`, `/feedback`, `/groups`, `/model`, `/movies/search` and admin routes
remain exposed. Unified intentionally disables the training worker and returns 403
from `/admin/retrain`, even with the admin header, to preserve the no-retraining
constraint. Standalone `tandem.api:app` retains main's admin-protected training behavior.
Only synthetic test catalogs and temporary checkpoints are trained by existing tests.

Main's `/groups` remains its in-memory recommendation-preview API, with per-member
and average-vector lists, optional mood boosts and caller-provided exclusions. Durable
QR/voting sessions use `/sessions`, with averaged individual scores, server-maintained
shown history, validated trailers and final voting rankings. Both use **MovieLens movie
IDs** externally. A group ID and a session ID are separate and cannot be interchanged.

`/health` includes main's `ok`, `w_version`, `movies`, `events`, `vision` fields plus
`status`. `/ready` checks SQLite and reports the loaded catalog and training status.

## SQLite schema and migration

`tandem/session_schema.sql` is an additive, idempotent SQLite migration. It adds:

- `tandem_profiles`: Google user ID and display name.
- `tandem_movies`: all 5,000 main catalog entries with MovieLens/TMDB IDs and immutable
  model vector indices.
- `tandem_movie_metadata`: provider/TMDB identity, original source ID, optional mapped
  MovieLens ID and the complete public movie metadata JSON.
- `tandem_sessions`, `tandem_members`, `tandem_invites`: host, lifecycle, heartbeat leases,
  member roles and SHA-256 hashes of random rotating invitation tokens.
- `tandem_queue`, `tandem_rounds`, `tandem_electorate`, `tandem_votes`: ordered queue,
  unique round UUIDs, fixed electorate snapshots and one vote per round/user.
- `session_feeds`, `session_predictions`, `vote_sync`: immutable session/feed associations,
  prediction tie-breakers and feedback synchronization markers.

Foreign keys, unique session/movie and round/user keys, a partial unique open-round
index, status/value checks, and `BEGIN IMMEDIATE` transactions enforce consistency.
Authorization is checked in the API/store for every operation; SQLite is never exposed
directly to phones. All database access shares main's connection lock. Accepted votes
and automatic round advancement commit together. Concurrent votes, duplicate requests,
stale round IDs, skips, end requests and expiry checks cannot advance a round twice.

Read-only source audit on 2026-10-24 found **200 movies**, **0 auth users**, and zero
profiles, sessions, members, invitations, rounds, queued movies, electorate rows or
votes. The complete movie snapshot is `catalog/session_movie_metadata.json`. No account
or live-session identity conversion is needed. Original source IDs are retained as
metadata only; they are not assumed to equal MovieLens IDs.

The SQLite `tandem_movies` table contains **all 5,000 MovieLens films**. The
5,000-movie JSON/NumPy model catalog is untouched. `GET /movies` provides authorized
pagination and reports `total: 5000`; `/ready` reports `sqlite_movies: 5000`. Exactly 63 metadata records map by
TMDB ID into that catalog; the other 137 are retained in SQLite without being offered
to a model that has no vector for them. Earlier YouTube verification accepted 62 of
those 63 in the US. Runtime rechecks public/embeddable, region and age restrictions;
provider errors fail queue preparation safely. No catalog was expanded or overwritten.

To copy the approved snapshot to an existing or new SQLite database:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/migrate_sqlite.py --database backend/data/tandem.db
```

This script never contacts Supabase. Inserts ignore existing provider IDs, preserving
hand-edited metadata and all existing feeds, events and model rows. It runs SQLite
integrity/foreign-key checks and reports before/after recommendation-table counts.
It is safe to repeat. SQLite runtime data is gitignored. Keep the remote source until
the team separately approves any decommissioning; this work performs no remote writes.

## Frontend sequence

1. Google sign-in, then `GET /me`. Create a feed using multipart `POST /feeds` with
   `tags` JSON or screenshots. Feed ownership comes from verified Google identity.
2. TV calls `POST /sessions` with `{"display_name":"TV"}`. The QR contains a frontend
   join URL with the returned invitation token in its fragment.
3. Phones call `POST /sessions/join` with `display_name` and `invite_token`. If a phone
   already has a feed, its latest feed is bound automatically. Otherwise it can onboard
   and attach its owned feed with `POST /sessions/{id}/feed` and `{"feed_id":"..."}`.
   Bindings cannot be replaced within an existing session; retries are idempotent.
4. Host calls `/queue`, then `/control` with `{"action":"start"}`. Queue batches use
   the unchanged pipeline's pick function over eligible trailers. Every queued/shown
   movie is excluded from later batches, with a database uniqueness backstop.
5. Phones heartbeat every 10 seconds and call `/votes` with `round_id` and value +1/-1.
   Only the caller's own vote changes. A snapshot electorate and 45-second leases keep
   disconnected phones from blocking completion. New joins wait until the next round.
6. Host can `/control` with `skip` plus `expected_round_id`, or `end`. Empty rounds do
   not spin automatically. Exhausting the queue returns to lobby; prepare/start again.
7. `GET /sessions/{id}/rankings` sorts completed rounds by unanimous approval, likes,
   dislikes, then predicted score. All accepted dislikes count even if their voter
   disconnects. Predictions never outrank unanimous positive votes.

`GET/POST /profiles/me` reads or changes only the caller's display name. Session
snapshots include member profiles; unrelated session data returns 404. `/session-catalog`
provides mapped movie metadata/trailer links. API schemas are generated in
[openapi-unified.json](openapi-unified.json) and served at `/docs`.

## Realtime and reconnect

Use authenticated **Server-Sent Events**, `GET /sessions/{id}/events`. Use `fetch` with
an Authorization header and parse SSE frames; native EventSource cannot set that
header. Do not put access tokens in URLs. Each `event: state` contains a complete
session snapshot; `id` is the persisted SQLite session revision. The stream checks for
changes every second and sends keepalives. Initial and reconnected streams always send
a fresh snapshot, so missed events do not require a replay log. Clients should apply
newer revisions and reconnect with a refreshed Google token after network/auth failure.
A member who leaves loses snapshot access and the stream emits `access_revoked`.

The TV stores only its session UUID. `frontend/session-client.js` restores Google
identity through `/me` and validates host ownership before reuse; network/401 failures
preserve the UUID for retry, rather than silently creating a new session. The UI must
provide a fresh Google ID token through `getToken`. Rotate the invitation after refresh
to display a new QR; raw invitation tokens are not stored by the helper.

The session snapshot is a consistent SQLite read transaction. Background sweeps and
feedback sync run every 10 seconds in the single service process. No Supabase Realtime,
RLS, secret/service-role access or database RPC is used by the active backend.

## Failure handling and persistence

Voting/advancement uses its own committed SQLite transaction. A separate, retryable
feedback transaction records `love`/+1 and `nah`/-1 using the original store's catalog
row-index format. Event and sync-marker writes commit together, avoiding partial
feedback replacement. A recommendation/provider or feedback failure never undoes an
accepted vote. Existing queues continue; retry queue preparation or use host skip/end.

Railway requires a persistent volume at `/data`, `TANDEM_DATA_DIR=/data`, one replica
and one Uvicorn worker. The manifest requires the mount and disables sleeping. Both
SQLite and existing model checkpoints must survive together. Local file-close/reopen
tests verify persistence; an actual Railway volume/restart and Docker image build have
not been exercised here. No deployment or push is performed. A wheel installation
must point TANDEM_CATALOG_DIR at the existing catalog plus metadata snapshot.

## Verification

```bash
PYTHONPATH=backend TANDEM_FAKE_ENCODER=1 backend/.venv/bin/python -m pytest backend/tests -q
node --test frontend/session-client.test.mjs
backend/.venv/bin/python -m build backend --outdir /tmp/tandem-sqlite-dist
```

The unified tests use real temporary SQLite databases for three phones and a TV,
concurrent voting/advancement, host controls, invitations, disconnects, authorization,
provider/feedback failure recovery, idempotent metadata copies, restart persistence,
SSE snapshots/reconnection, original recommendation routes and the exported contract.
Main's recommendation tests remain unchanged. Historical Supabase migrations stay in
`supabase/migrations` solely to preserve the already-applied remote history.
