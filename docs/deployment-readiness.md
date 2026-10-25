> **Historical Supabase design below.** The active backend now uses SQLite and Google auth; see [unified-backend.md](unified-backend.md) for the current schema, API, SSE, migration and deployment contract. No Supabase configuration is needed.

> Unified backend update: see [unified-backend.md](unified-backend.md) for the current entrypoint, authenticated recommendation routes, feed attachment, trailer checks and Railway persistence. Earlier standalone/mock instructions below describe the session-only service.

# FastAPI deployment readiness

Review date: 2026-10-24 (America/Chicago). Nothing has been deployed.

Verified in this preparation: live TV/three-phone API lifecycle (108.544s), live
Realtime delivery/isolation/reconnect (15.556s), 16 offline Python tests, three TV
helper tests, fresh wheel/sdist build, lint, and OpenAPI drift check. Post-test
inspection found zero generated fixture users, zero fixture movies, and zero
remaining sessions. Eight application tables still enforce RLS, six remain
published, and the original two migration history entries are unchanged.

No permanent schema changes were made. The original recommendation module is
unchanged. A subsequently approved TMDB import added 200 trailer-bearing movie
records; repeating the same source set added zero duplicates.

## Recommended hackathon approach

Use **one always-on Render Python web service**, one Uvicorn worker, with Supabase
remaining the database/Auth/Realtime service. This fits the existing FastAPI lifespan
worker without introducing queues or another datastore. Select a paid always-on
instance rather than relying on a free service that can sleep. Current Render
free services spin down after 15 minutes without inbound traffic; a stopped API
cannot run expiry sweeps. See [FastAPI deployment](https://render.com/docs/deploy-fastapi)
and [free-service limits](https://render.com/docs/free).

Proposed commands, from repository root (review only):

```bash
# Build
pip install -r backend/requirements.lock
pip install --no-deps ./backend
# Start (Render sets PORT)
uvicorn app:app --host 0.0.0.0 --port "$PORT" --workers 1
```

Use a supported Python version such as 3.12, then validate the lockfile on that
version before deployment. Current build/tests ran on Python 3.9.6 on macOS;
there has not been a Linux/3.12 deployment smoke test. The lock includes dev tools;
that is acceptable for the hackathon but can be split later.

## Background tasks

The lifespan starts one sweep task per process. `SWEEP_ENABLED=true` (default)
checks sessions every 10 seconds. Each call uses service_role-only sweep_sessions;
SQL locks each session and uses SKIP LOCKED. Multiple instances cannot double-advance,
but extra workers duplicate scans and API traffic. Start with one worker. FastAPI
workers are separate processes: [worker documentation](https://fastapi.tiangolo.com/deployment/server-workers/).

`SWEEP_ENABLED=false` disables the task for fixture-isolated integration tests or
for API replicas only if another always-running worker owns sweeping. Never
disable every sweeper in a deployed system. No separate sweep service is included.
Serverless platforms that freeze between requests are unsuitable for this task.
Shutdown cancels/awaits the sweep then closes the shared HTTP client. Restarting
recovers durable state from Postgres; expiry can be delayed during downtime.

Sweep catches upstream HTTP failures and logs a retry message. It is not supervised
against unexpected programming exceptions, and /health does not detect a stopped
sweep or bad credentials. Before public launch add monitoring for sweep failures
and database/Auth availability; a durable external scheduler is the later upgrade.
The global sweep can lock many active sessions in one transaction; adequate for
hackathon scale, measure before scaling it to many rooms.

## Environment and CORS

| Variable | Required / scope |
| --- | --- |
| SUPABASE_URL | Exact tandem URL; no trailing-path components |
| SUPABASE_PUBLISHABLE_KEY | Public application key used with caller JWTs |
| SUPABASE_SECRET_KEY | Server-only key for sweeps; required at startup |
| FRONTEND_ORIGINS | Comma-separated exact origins including scheme and port; whitespace trimmed |
| SWEEP_ENABLED | true for the single proposed web service |
| PORT | Hosting platform port, passed to Uvicorn command |

No .env file is loaded automatically. Configure the platform secret manager;
never bake backend/.env.test into an image or commit it. Set the exact approved
HTTPS frontend origin; retain localhost only when useful for development. Origins
contain no route path or trailing slash. Do not use `*` as a substitute for auth.
Bearer tokens, not cross-origin cookies, authenticate API requests. Preflight
allows GET/POST and Authorization/Content-Type. Browsers connect to Supabase
Realtime directly; this backend does not proxy WebSockets.

Supabase Anonymous Sign-Ins must be enabled for the guest browser flow. Live tests
provision confirmed password users with the admin API; they do not verify that
the anonymous provider is enabled or CAPTCHA is configured. Verify guest sign-in
from the actual frontend before demo day. Auth redirect/site URLs are separate
Supabase settings when using permanent account flows.

## Database and HTTP connections

FastAPI uses one httpx.AsyncClient per process with a 15-second timeout, reused
and closed in lifespan. Each request provides its own Authorization header;
credentials are never mutated on a shared client. The service talks HTTPS to
Supabase Auth/PostgREST, not directly to Postgres. No DATABASE_URL, database
password, psycopg pool, or Supavisor configuration is required for the current app.

Database writes stay in short atomic RPC transactions. No recommendation/network
work runs under the session lock. Network loss after commit can make the HTTP
outcome uncertain: round-ID retries are safe, session creation/rotation require
recovery. GET state spans multiple queries, so clients refetch after notifications.
The current 100-row mock catalog boundary is unchanged; replacing the recommender
or implementing catalog pagination is outside this work.

## Remaining launch checks

- Confirm exact frontend origin, HTTPS backend URL, and anonymous Auth configuration.
- Run the documented API and Realtime suites against the approved tandem project;
  cleanup is scoped to generated identities/provider IDs and never resets schema.
- The TMDB catalog is seeded with 200 movies; verify attribution and trailer playback.
- Verify restored TV/phone sessions and trailer playback in actual browsers.
- Check secrets are absent from tracked files; use /health for liveness only.
- Smoke-test the package on the target Linux/Python runtime before deploying.

This is a recommendation and readiness review, not authorization to deploy.
