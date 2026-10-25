# Decisions

One line each: date, decision, why.

- 2026-10-24: Supabase Auth/Postgres/Realtime with FastAPI via caller-JWT REST/RPC; keep authorization in database and server secrets out of clients.
- 2026-10-24: UUID voting rounds and session-row locks serialize votes, skips, and sweeps; derive current round instead of circular foreign keys.
- 2026-10-24: Snapshot electorate with 45-second heartbeat leases and a 10-second backend sweep; TV host does not vote by default.
- 2026-10-24: Store SHA-256 hashes of rotating random QR invitation tokens in private schema; defer embeddings and use only a mock recommendation provider.
- 2026-10-24: Use existing tandem for authorized hackathon live tests with generated fixture namespaces and scoped cleanup; disable the global sweep during tests.
- 2026-10-24: Export typed FastAPI OpenAPI and test the real Realtime wire protocol; defer TMDB writes until source/destination approval and keep inserts conflict-ignoring.
