# Tandem backend

FastAPI with Supabase Auth, Postgres RPCs, and Realtime.
Database migrations are in ../supabase/migrations; recommendation integration
uses the separate protocol and mock in recommendations.py.

## Install

From the repository root:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install pip==25.3
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install --no-deps -e backend
```

Export SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY, and
FRONTEND_ORIGINS (comma-separated browser origins). Never commit local credentials.
Enable Supabase Anonymous Sign-Ins for guest phones and TV.

## Run

```bash
backend/.venv/bin/uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000
```

API documentation: /docs. Liveness: /health. All session operations require a
Supabase user bearer token; RLS and host-checked RPCs protect mutations.
The lifespan sweeper checks disconnected voters every 10 seconds; keep one
worker running with SWEEP_ENABLED=true (default). SWEEP_ENABLED=false is for
isolated integration tests or replicas with another active sweeper.

The service includes session creation/join, rotating hashed QR invitations,
round-specific votes, atomic advancement, host skip/end, and heartbeat/leave.
