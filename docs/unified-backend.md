# Unified backend integration

Run `uvicorn unified:app --app-dir backend` from the repository root after installing
`backend/requirements.txt` and PyTorch. Docker and Railway use this entrypoint.
Neither catalog nor Supabase schema changes are required. No deployment is performed.

## Responsibilities and lifecycle

`unified.py` owns one Supabase HTTP client, expiry sweeper, recommendation catalog,
frozen encoder, SQLite store and feedback reconciler. Both route sets appear in
`/docs` and `/openapi.json`; `/health` retains `{ "status": "ok" }`, while `/ready`
reports catalog size and model version. The recommendation trainer loads the existing
accepted checkpoint but its worker never starts. `/admin/retrain` returns 403.
Standalone `tandem.api:create_app` retains legacy behavior for the existing algorithm
tests; do not deploy that unauthenticated development entrypoint.

`session_recommendations.py` is the adapter. `mean_scores` is an injected aggregation
function, separate from the existing `score_feed` and `pick` functions. It averages
connected voters' attached-feed scores (45-second heartbeat lease) and applies the existing ranking/exploration policy to
eligible movie indices. Model, loss, embeddings, ranking algorithm and checkpoints
are unchanged. Session feedback is recorded for future use but does not train a model.

## Frontend sequence and authentication

All session and recommendation routes require a Supabase user access token in
`Authorization: Bearer ...`. Supabase Auth verifies it. Feed creation ignores the
multipart `user` field for ownership and uses the authenticated UUID. Legacy anonymous
feeds cannot be claimed by guessing their IDs. Cross-user feed reads, favourites and
feedback return 404. `/health`, `/ready` and generated documentation are public.

1. TV calls `POST /sessions` with `{ "display_name": "TV" }`.
2. Phones join through `POST /sessions/join` with the invitation token and name.
3. Each phone calls `POST /feeds`, multipart `tags` containing a JSON numeric weight
   map (or `files` containing screenshots when the optional Llama key is configured).
4. Each phone attaches its owned feed using `POST /sessions/{id}/feed` with
   `{ "feed_id": "..." }`. Attachments are idempotent and immutable within a session;
   replacing one returns 409. This prevents old votes being attributed to a new feed.
5. Host calls `POST /sessions/{id}/queue`, then `/control` with `{ "action": "start" }`.
   At least one voter feed must be attached. Voters without a feed can still vote.
6. Phones heartbeat and vote through existing endpoints. Supabase remains authoritative
   for round IDs, eligibility, atomic advancement and disconnect leases. No algorithm
   call runs in the accepted-vote path. Realtime subscriptions remain unchanged.
7. Fetch `GET /sessions/{id}/rankings` for final results. Completed rounds sort by
   unanimity first, likes descending, dislikes ascending, then predicted score descending.
   Unanimity requires at least one vote, all accepted votes positive, and votes from
   every non-excluded round participant. Accepted dislikes still count after a disconnect. Skipped,
   ended or unfinished rounds are omitted. Predictions never outrank unanimous approval.
8. Host ends through `/control` with `{ "action": "end" }`.

When a queue runs out the session returns to lobby. Host prepares another batch and
starts it. A queue request uses the existing pipeline's batch size, not all 100 slots.
Restore the TV's stored auth session and group UUID after refresh, fetch the existing
session snapshot, resubscribe, then fetch again after subscription confirmation or
reconnection (see frontend-integration.md). SQLite bindings survive server restarts;
clients do not need to attach the same feed again, though repeating attachment is safe.

## IDs, eligibility and trailers

The four namespaces are distinct: MovieLens `movie.id`, catalog row index, TMDB
`movie.tmdb_id`, and Supabase `movies.id`. Join catalog `tmdb_id` to Supabase
`provider='tmdb'` plus `provider_movie_id`; reject missing or ambiguous matches.
`/feedback`'s `movie_id` is a **MovieLens ID**. Session queue/vote/ranking IDs refer to
**Supabase IDs**. Feedback storage uses the mapped catalog row index. Do not rebuild
or reorder the catalog while retaining existing SQLite events or model checkpoints.

Read-only audit on 2026-10-24: 5,000 MovieLens movies, 200 Supabase movies, **63 exact
TMDB matches**. All 63 returned video metadata from YouTube's public oEmbed endpoint.
This proves public metadata availability, not actual playback on every TV or region.
After the local key was corrected, YouTube Data API checks verified **62 of 63**
as public, embeddable, not age restricted and available in the US; the remaining
movie is excluded. See [the audit](trailer-audit.json). Actual TV playback remains
a device check. No catalog entries were inserted, updated or deleted. Reproduce with:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/audit_trailers.py /path/to/movies-export.json
```

The adapter accepts only HTTPS YouTube URLs with valid video IDs and successful
YouTube Data API verification of public/embeddable status, region restrictions and
age restrictions. `YOUTUBE_API_KEY` is required for queue preparation; `TRAILER_REGION`
defaults to US. Keyless oEmbed checks remain available in the audit script but cannot
establish playback eligibility and are not a runtime fallback. Invalid/unavailable
videos are excluded. Missing keys or network/provider failures return a retryable 503;
votes and host controls remain available. Successful checks cache for one hour.
No provider check guarantees device playback: TV clients must handle YouTube player
errors and let the host skip the exact current round. The existing skip endpoint
requires `expected_round_id`; a stale skip cannot advance a newer round.

All queued movies, including every shown movie, are excluded from subsequent picks.
The database's unique session/movie constraint independently prevents races/repeats.
No title guessing or fallback to the other 137 Supabase movies occurs.

## Failure recovery and feedback

Queue failures leave votes and existing queues intact: 409 means no attached feed or
no eligible movies; 503 means retry queue preparation later. Existing queued rounds
continue; the host can skip/end even during a recommendation outage. Never retry a
vote merely because recommendation synchronization is delayed. Re-fetch session state
when an HTTP request's outcome is uncertain.

Every 10 seconds the reconciler reads confirmed Supabase votes for sessions with feed
bindings, maps movie IDs, and writes `love` for +1 or `nah` for -1 to the original store.
It also sees direct Supabase RPC votes. It never assumes a successful stale vote request
inserted a vote. SQLite `vote_sync` markers deduplicate completed writes. A crash between
an event write and its marker replays that same label; the store replaces the existing
feed/movie label. Transient failures retry after restart. This is eventually consistent
across two databases, not a distributed transaction. Votes from users without attached
feeds or unmapped catalog movies cannot be mirrored. The source votes remain intact.

Integration adds only three **SQLite** tables: session_feeds, session_predictions and
vote_sync. Supabase migrations, RLS, publications, data and credentials are unchanged.

## Railway and persistence

Use backend as the service root, its Dockerfile, **one replica and one Uvicorn worker**.
The Railway manifest requires `/data`, pins one replica and disables sleeping.
Mount a Railway persistent volume at `/data` and set `TANDEM_DATA_DIR=/data`. Persist
`tandem.db` and `checkpoints/` together. Existing deployed data must be backed up and
copied to the volume before replacing an ephemeral deployment; do not initialize over
or delete the previous store. No such migration or deployment has been done here.
Startup refuses a Railway environment without the `/data` volume declaration or with
a different data directory. Local tests close and reopen a real SQLite file to verify
feeds, bindings, votes and synchronization markers survive a restart. A remote volume
has **not** been provisioned or restart-tested; environment declarations alone do not
prove the remote mount is operational. Without persistent storage this deployment is
unsupported and feed ownership/bindings would be lost on redeploy.

Required server environment: SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY,
SUPABASE_SECRET_KEY, FRONTEND_ORIGINS (exact comma-separated origins).
YOUTUBE_API_KEY is also required to prepare recommendation queues.
Optional: LLAMA_API_KEY, LLAMA_BASE_URL, LLAMA_MODEL for screenshots;
TRAILER_REGION for trailer checks;
TANDEM_CATALOG_DIR (default bundled backend/catalog), TANDEM_DATA_DIR;
SWEEP_ENABLED (true normally, false for fixture-isolated tests).
Do not set TANDEM_FAKE_ENCODER=1 in deployment. No training-enable variable is exposed.
Use ignored local environment files or Railway secret variables. Docker excludes
`.env*`, runtime databases, local environments and build output.

## Verification

```bash
PYTHONPATH=backend TANDEM_FAKE_ENCODER=1 backend/.venv/bin/python -m pytest backend/tests -q
node --test frontend/session-client.test.mjs
backend/.venv/bin/python -m build backend --outdir /tmp/tandem-unified-dist
```

A wheel installation must set TANDEM_CATALOG_DIR to the existing catalog directory;
the Docker image copies both catalog files explicitly.

The existing training tests train only synthetic catalogs and temporary checkpoints.
The new unified integration test uses a stateful Supabase double and a temporary SQLite
file; it covers three phones, ownership, queue selection, voting/advancement, feedback
replay, rankings, termination, restart persistence, and existing recommendation routes.
The live API and Realtime suites also passed against uniquely scoped development
fixtures during this integration. They remain separate and skip without explicitly
exported test credentials. They create isolated fixtures; do not enable them against production.
