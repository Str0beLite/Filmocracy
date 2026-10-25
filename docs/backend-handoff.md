> Unified backend update: see [unified-backend.md](unified-backend.md) for the current entrypoint, authenticated recommendation routes, feed attachment, trailer checks and Railway persistence. Earlier standalone/mock instructions below describe the session-only service.

# Tandem backend handoff for teammate agents

Start here before changing the frontend, recommendation integration, or backend.
This records the backend work already implemented, not a request to build it again.
The backend owner handles Supabase/FastAPI; separate teammates own the UI and
recommendation algorithm. `docs/idea.md` is still a blank template: the implemented
backend scope is recorded in [backend-plan.md](backend-plan.md).

## Current state

- FastAPI service, Supabase Auth integration, protected database RPCs, and RLS exist.
- Eight public application tables and one private invitation table are implemented.
  Both versioned migrations were applied to tandem; do not reapply them manually.
- The approved development project is tandem (`jwrfdwwpndlorrmhmwuw`). It is shared
  by the team, not a disposable database. Do not reset, truncate, drop, or delete
  unrelated records. Ask the backend owner before changing the existing schema.
- The catalog contains 200 imported TMDB movies with trailer links and posters.
  An identical import added zero duplicates. Playback has not been browser-tested.
- No embedding table or recommendation algorithm was implemented. The provider is
  a catalog-order mock. No service has been deployed or pushed by this agent.

## Read these contracts

| Need | Start with |
| --- | --- |
| Backend installation, environment variables, and test commands | [backend/README.md](../backend/README.md) |
| Frontend requests, responses, errors, QR flow, reconnect, subscriptions | [frontend-integration.md](frontend-integration.md) |
| Machine-readable API contract | [openapi.json](openapi.json) |
| Tables, relationships, constraints, RLS, and atomic round lifecycle | [backend-plan.md](backend-plan.md) |
| TMDB import behavior and attribution | [movie-catalog.md](movie-catalog.md) |
| Worker lifecycle, CORS, connections, and deployment limits | [deployment-readiness.md](deployment-readiness.md) |
| Reasons behind architecture choices | [decisions.md](decisions.md) |

The authoritative code is below. If a contract changes, update its implementation,
tests, frontend guide, and exported OpenAPI together.

| File | Responsibility |
| --- | --- |
| `backend/app.py` | Auth verification, HTTP endpoints, Supabase REST/RPC client, lifespan sweeper |
| `backend/api_models.py` | Response and error models used by OpenAPI |
| `supabase/migrations/20261025000706_movie_voting_backend.sql` | Tables, RLS, grants, database functions, Realtime publication |
| `supabase/migrations/20261025001329_explicit_invitation_deny.sql` | Explicit denial of client access to invitation hashes |
| `backend/recommendations.py` | RecommendationProvider protocol, context, and mock; integration boundary only |
| `backend/import_tmdb.py` | Insert-only, conflict-ignoring catalog ingestion; dry-run by default |
| `frontend/session-client.js` | Framework-independent TV identity/session restoration helper |
| `backend/tests/` | Local tests, opt-in live tests, fixture cleanup, SQL verification |
| `backend/scripts/export_openapi.py` | Regenerates docs/openapi.json from the actual app |

## Rules the frontend must preserve

Each phone and TV has its own Supabase Auth identity. Restore the existing Auth
session before anonymous sign-in. Keep a singleton browser Supabase client with
persistSession/autoRefreshToken enabled and persist the group-session UUID
separately. The supplied TV helper checks host ownership when restoring. Clearing
browser storage loses guest ownership; a QR invitation is not host authentication.

Create a session on the TV, join phones through the invitation token, prepare the
queue, then start. Display the QR from a frontend join URL; FastAPI does not render
QR images. Invitation tokens are random, rotating, expiring, and stored only as
hashes in the private schema. Only the host can rotate, start, skip, or end.

Send the current voting-round UUID with every vote and expected_round_id with
every skip. Likes are +1, dislikes -1. A stale request can return HTTP 200 with the
new current round without storing the old vote; refetch instead of replaying that
preference onto a new movie. The database, not a client-side vote counter, advances
the session. Session-row locks and the single-open-round index prevent duplicate
advancement under concurrent votes/skips.

TV hosts are nonvoters by default. Voters are snapshotted when each round opens;
late joiners and excluded reconnecting phones wait for the next round. Phones
heartbeat every 10 seconds. After 45 seconds without a heartbeat, expiry checks
exclude that voter. FastAPI's enabled sweeper checks every 10 seconds. Keep the
process running; a frozen/serverless process cannot maintain that schedule.

Read the current round from voting_rounds where closed_at is null; there is no
current_movie_id on group_sessions. An exhausted queue returns to lobby. A round
with no votes waits for host action. Shown history uses session_movies.shown_at.

Subscribe to the six published session tables, then fetch state; refetch after
reconnect and mutations. Treat events as invalidations. GET state spans multiple
queries, so do not assume a transactionally consistent snapshot. Movie metadata
and member display names are read directly from Supabase, as documented in the
frontend guide. The FastAPI service has no movie-list endpoint.

RLS protects session INSERT/UPDATE data delivery; joining a Postgres Changes
channel alone does not grant row access. Private Broadcast/Presence policies are
not implemented. Review the documented DELETE-event limitations before adding
private administrative deletion notifications.

## Rules for recommendation integration

Coordinate with the algorithm teammate; do not implement or replace their ranking
logic here. The existing provider returns ordered database movie IDs. Its current
context contains session_id, catalog_movie_ids, and shown_movie_ids; the queue
endpoint currently passes already queued IDs as the exclusion set too. The mock
uses the first 100 catalog IDs even though the catalog contains 200 movies.

Connect the teammate's provider at the existing boundary in app.py, agreeing on
any additional context fields together. Do external algorithm/API work before
entering database transactions. Install returned IDs through host-authorized
enqueue_movies, then let the existing database round lifecycle advance them.
Do not add embeddings until the model version and dimensions are agreed.

## Verification and safe development

Use [backend/README.md](../backend/README.md) for setup. Local credentials are
uncommitted; agents on another checkout must configure their own environment.
No .env files, API tokens, or service keys should enter commits, prompts, or logs.
Browsers use only the publishable key plus their own user JWT; the server-only
key belongs in backend configuration.

```bash
backend/.venv/bin/python -m unittest discover -s backend/tests -v
node --test frontend/session-client.test.mjs
backend/.venv/bin/ruff check backend
backend/.venv/bin/python -m build backend
backend/.venv/bin/python backend/scripts/export_openapi.py
```

Default discovery skips the two live tests unless TEST_* variables are exported;
a skip is not a live pass. Live tests create unique users/sessions/movie namespaces,
disable the global sweep, and clean up only their fixtures. Use the documented
opt-in command; never clean up by deleting all users or all movie rows. Prefer
three_phones.sql for rollback-only SQL checks; the older database.sql calls a
global sweep and is unsuitable around unrelated active development sessions.

Latest commit-preparation checks: 16 local Python tests, three TV tests, scoped
rollback SQL, live Realtime, full/staged builds, and lint passed. The live API test
passed during earlier integration preparation, but its latest reruns failed with
upstream ReadTimeout/503 errors. Do not report those reruns as passing or silently
disable assertions. Physical-device UI testing, anonymous guest-provider setup,
target deployment-runtime testing, and trailer playback still need verification.

## Commit map

| Commit | Work included |
| --- | --- |
| `0c9fb12` | Supabase schema, RLS, round lifecycle, SQL tests |
| `f7dcb29` | Recommendation contract and mock only |
| `863850f` | Auth/session/QR/voting API, sweeper, package setup |
| `c1f1968` | TV identity restoration and tests |
| `1e00c7e` | TMDB importer and its tests |
| `7df4412` | Live/local tests, OpenAPI export, frontend and deployment documentation |

Pre-existing agent configuration changes were intentionally left uncommitted.
Do not bundle those or other teammates' changes into backend fixes automatically.
