# Tandem backend

FastAPI + Supabase Postgres/Auth/Realtime. Schema and relationships are documented
in [the backend plan](../docs/backend-plan.md); versioned SQL is in
[`supabase/migrations`](../supabase/migrations). Embeddings are deferred.

## Setup and run

Python 3.9+; from the repository root:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install pip==25.3
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install --no-deps -e backend
```

Create an ignored local backend/.env with SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY,
and SUPABASE_SECRET_KEY. Enable **Anonymous Sign-Ins** in Supabase Auth for guest phones and TV. Set
FRONTEND_ORIGINS to the frontend origins, comma-separated. With those variables
exported into the shell, one command runs the service and disconnect sweeper:

```bash
backend/.venv/bin/uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000
```

The server does not load .env automatically: use your environment manager or
`set -a; source backend/.env; set +a` before running it. API docs: /docs.
Health: /health. Never place SUPABASE_SECRET_KEY in frontend variables.

Frontend developers: start with [the integration guide](../docs/frontend-integration.md)
and [generated OpenAPI](../docs/openapi.json). Deployment is reviewed in
[deployment readiness](../docs/deployment-readiness.md); nothing is deployed.

## API contract

All endpoints except /health require Authorization: Bearer <Supabase user JWT>.
Supabase Auth verifies the token; user database calls forward that JWT, so RLS
and auth.uid() remain effective. Direct browser RPC calls enforce the same rules.

| Endpoint | Body / behavior |
| --- | --- |
| POST /sessions | `{ "display_name": "TV" }`; returns session_id + invite_token |
| POST /sessions/join | `{ "display_name": "Alice", "invite_token": "…" }` |
| GET /sessions/{id} | Member-only session state, rounds, electorate, votes, queue |
| POST /sessions/{id}/invitation | Host rotates invitation and receives new token |
| POST /sessions/{id}/queue | Host appends mock provider's catalog IDs, idempotently |
| POST /sessions/{id}/control | `{ "action": "start" }`, `skip` with expected_round_id, or `end` |
| POST /sessions/{id}/votes | `{ "round_id": "UUID", "value": 1 }`; -1 for dislike |
| POST /sessions/{id}/heartbeat | Phone renews lease every 10 seconds |
| POST /sessions/{id}/leave | Stops participating immediately |

The QR encodes a frontend join URL (prefer `/join#token=…` to avoid server access
logs containing invitation tokens). The frontend extracts the fragment and sends
the token in the join request body. The database stores only its SHA-256 hash.

Create -> phones join -> queue -> host starts -> phones heartbeat/vote. Current
round is the voting_rounds row with closed_at NULL. The TV is a nonvoting host.
New members wait until the next round. Expired voters cannot reenter the same
electorate. A round needs at least one vote before it completes automatically;
an empty/disconnected room waits for host skip/end. When the queue is exhausted,
the session returns to lobby; prepare another queue then start again.

Only the sweep uses the server secret. Keep the service running: it checks leases
and session expiry every 10 seconds. Votes and heartbeats also check expiry. A
disconnected voter stops blocking after 45 seconds plus up to 10 seconds for sweep.
Multiple backend workers are safe because the database serializes each session.
Use one worker for the demo to avoid duplicate sweeps. SWEEP_ENABLED=false is used
only by fixture-isolated tests, or when another process explicitly owns sweeping.

The public tables deny direct mutations except a user's own profile name.
Session writes use identity-checked RPCs; no request accepts a user_id to vote for.
Session members can see each other's votes. RLS isolates unrelated sessions.

## Recommendation integration

`recommendations.py` defines RecommendationProvider and RecommendationContext.
Replace the provider instance in app.py when the teammate's implementation is
ready. MockRecommendationProvider preserves catalog order, removes queued/shown
IDs and duplicates, and limits the list. It computes no recommendations.
The mock reads the first 100 catalog IDs; it is a demo fixture, not a catalog
paginator. Import actual movie metadata with server-side tooling before the demo.
No movies or embedding vectors are seeded by migrations.

Provider work runs outside database locks. Queue installation is atomic and
host-only; votes atomically close the current round and open a queued movie.
No external API or algorithm call happens inside a voting transaction.

## Verification

```bash
backend/.venv/bin/python -m unittest discover -s backend/tests -v
node --test frontend/session-client.test.mjs
backend/.venv/bin/ruff check backend
backend/.venv/bin/python -m build backend
```

Run tests/database.sql through Supabase SQL tooling as postgres (or psql with
ON_ERROR_STOP=1). It impersonates authenticated users and service_role, asserts
authorization/lifecycle/constraints/publication behavior, and rolls back fixtures.
Do not execute it using a public client or the service-role REST API.

Migrations were applied to tandem and these database tests were run there. A
separate two-transaction concurrent-vote check stored both final votes and
opened exactly one successor; its temporary committed fixtures were deleted.
SQL rollback tests can consume identity sequence values; gaps are harmless.

For another project, link using Supabase CLI then use `supabase db push`. Do not
reapply SQL manually to tandem: its migration history already records these files.

## Live API and Realtime tests

The existing tandem project is approved for hackathon development/testing. Both
migrations and all eight application tables were inspected before live writes.
backend/.env.test is gitignored and must remain local, owner-readable only. Set
TEST_SUPABASE_URL, TEST_SUPABASE_PUBLISHABLE_KEY, TEST_SUPABASE_SECRET_KEY,
TEST_PROJECT_REF, TEST_ALLOW_WRITES=1, and TEST_ALLOW_EXISTING_PROJECT=1 for the
approved tandem development project. Never print or commit this file.

```bash
set -a
source backend/.env.test
set +a
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_live*.py' -v
```

Without test settings, live tests report SKIPPED, not a live pass. The API test
uses real Auth -> FastAPI ASGI HTTP -> Supabase, simulating TV, three phones, and
an outsider. It waits for a real 45-second lease to expire, so allow about 1–2
minutes. Recommendation code is neither changed nor invoked; the host enqueues
the run's own fixture movie IDs through the database integration boundary.

The Realtime test opens actual WebSockets using Supabase's documented JSON 1.0
protocol and the dev-only websockets dependency. It checks all six published
tables, an outsider receiving no row events, refreshed-identity reconnection,
and a snapshot containing votes missed while disconnected. Postgres Changes row
authorization is separate from rejecting a channel join; see the frontend guide.

Each live test generates uniquely named confirmed Auth users and a unique movie
provider namespace. Cleanup deletes sessions hosted by those generated identities,
then those users, and movies with that exact provider namespace. Cleanup failures
fail the suite and identify the run ID for targeted investigation. The tests never
reset, truncate, drop, or migrate the database. The background global sweep is
disabled during tests to avoid touching unrelated development sessions. SIGKILL
can bypass cleanup; do not compensate with unscoped deletes.

tests/three_phones.sql is a separate rollback-only database verification with all
queries scoped to its own fixtures; it does not call the global sweep. It has run
successfully against tandem. The older database.sql remains historical verification;
prefer the scoped test when unrelated development sessions may exist.

## Catalog preparation

[TMDB import plan and commands](../docs/movie-catalog.md). The importer is dry-run
by default, inserts only missing movie IDs, and has no writes to other tables.
The approved import added 200 TMDB movies with trailer URLs to tandem. Repeating
the same source set added zero duplicates. Importer unit tests use synthetic TMDB
responses; trailer playback still needs verification in the intended browser.
