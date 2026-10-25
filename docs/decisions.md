# Decisions

One line each: date, decision, why.

- 2026-10-25: Backend is one FastAPI process (serving + background trainer thread). W is ~6k params, so retraining takes seconds on CPU and needs no separate worker or GPU.
- 2026-10-25: Host on Railway (Dockerfile, volume at `/data` for SQLite + W checkpoints). HF Spaces is the free fallback, but its disk is wiped on restart.
- 2026-10-25: Open-vocabulary tags: every tag string is embedded with frozen `bge-small-en-v1.5` (not an LLM); a feed or film = weighted mean of its tag embeddings. W = I + ABᵀ (384×384, rank 8), so no fixed tag lists or hand-made prior. Replaces the fixed 132-tag × movie-tag W.
- 2026-10-25: Only LLM step is screenshot → free-form tags, using Meta Llama vision (Llama API, OpenAI-compatible). No LLM on the movie side.
- 2026-10-25: Loss = taste term (cos(Wx, mean loved-film tags)) + InfoNCE ranking with thumbs-downs as hard negatives + λ‖ABᵀ‖².
- 2026-10-25: Live loop retrains on the whole buffer every 20 events and swaps W only if held-out recall@50 doesn't drop.
- 2026-10-24: Algorithm API is keyed by user id / group id, never raw embeddings. A user's embedding = their latest feed's x and stays server-side, so every call scores with the live W.
- 2026-10-24: Group = in-memory session with the members' latest feeds and their averaged x. `POST /groups/{gid}/recs` returns one list per member + one from the average; choosing the trailer from those lists is a later layer.
- 2026-10-24: Mood = tag boost: +0.15 to films whose catalog tags match any requested tag, before ranking. No algorithm change.
- 2026-10-24: Groups live in memory (lost on restart). Feeds, votes and W stay in SQLite on the Railway volume.
- 2026-10-24: Google sign-in required; backend verifies the GIS ID token (`google-auth`) and uses `sub` as the user id. `TANDEM_DEV_AUTH=1` bypass for local dev only.
- 2026-10-24: Catalog = top 5000 MovieLens 25M films with tag-genome scores, committed. Posters/trailers come from TMDB on the fly in the frontend by `tmdb_id`, not baked into the catalog.
- 2026-10-24: Frontend on Vercel (`VITE_API_URL` → Railway domain).
- 2026-10-24: Supabase Auth/Postgres/Realtime with FastAPI via caller-JWT REST/RPC; keep authorization in database and server secrets out of clients.
- 2026-10-24: UUID voting rounds and session-row locks serialize votes, skips, and sweeps; derive current round instead of circular foreign keys.
- 2026-10-24: Snapshot electorate with 45-second heartbeat leases and a 10-second backend sweep; TV host does not vote by default.
- 2026-10-24: Store SHA-256 hashes of rotating random QR invitation tokens in private schema; defer embeddings and use only a mock recommendation provider.
- 2026-10-24: Use existing tandem for authorized hackathon live tests with generated fixture namespaces and scoped cleanup; disable the global sweep during tests.
- 2026-10-24: Export typed FastAPI OpenAPI and test the real Realtime wire protocol; defer TMDB writes until source/destination approval and keep inserts conflict-ignoring.
