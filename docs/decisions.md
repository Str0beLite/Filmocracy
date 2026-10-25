# Decisions

One line each: date, decision, why.

- 2026-10-24: Supabase Auth/Postgres/Realtime with FastAPI via caller-JWT REST/RPC; keep authorization in database and server secrets out of clients.
- 2026-10-24: UUID voting rounds and session-row locks serialize votes, skips, and sweeps; derive current round instead of circular foreign keys.
- 2026-10-24: Snapshot electorate with 45-second heartbeat leases and a 10-second backend sweep; TV host does not vote by default.
- 2026-10-24: Store SHA-256 hashes of rotating random QR invitation tokens in private schema; defer embeddings and use only a mock recommendation provider.
- 2026-10-24: Use existing tandem for authorized hackathon live tests with generated fixture namespaces and scoped cleanup; disable the global sweep during tests.
- 2026-10-24: Export typed FastAPI OpenAPI and test the real Realtime wire protocol; defer TMDB writes until source/destination approval and keep inserts conflict-ignoring.

- 2026-10-24: Unified FastAPI serves session and recommendation routes; SQLite stores feed ownership/bindings and replay markers, group scores average existing predictions, Supabase owns atomic voting, training stays disabled, and Railway requires a /data volume.


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
- 2026-10-24: Dropped the first Supabase session service (app.py, sessions/rounds/votes RPCs) in favour of the algorithm service; Supabase stays and will be rewritten around the algorithm's API. Its applied migrations stay in `supabase/migrations/` so `supabase db push` history matches the live project.
- 2026-10-25: Commit a pre-trained W (`backend/catalog/w_seed.pt`); a fresh database starts from it instead of W = I. Trained on 60 synthetic persona users (`scripts/seed_fake.py`, ids `fake-*`, with a popularity pull) + team ratings; recall@50 0.33 → 0.51. Drop the fake data once real users arrive.
- 2026-10-25: Favourites accept exact `movie_ids`; the holdout split is seeded per film so one-at-a-time favourites still split ~30%.

- 2026-10-24: Integration branch retains every upstream recommendation endpoint and Google-auth standalone mode; unified production injects Supabase JWT identities, keeps durable session voting and disabled training, and leaves legacy /groups ephemeral. Google GIS clients exchange their ID token through Supabase Auth before calling unified endpoints.

- 2026-10-24: User requested all Supabase functionality move to main's SQLite database; retain Google auth/MovieLens identities, additive transactional session tables, authenticated SSE instead of Supabase Realtime, all 200 source movie records and unchanged remote data/model checkpoints.

- 2026-10-25: Use authenticated WebSockets for phone/TV session snapshots and heartbeats; retain HTTP mutation transactions and SSE compatibility, with SQLite revisions providing reconnect synchronization.
- 2026-10-25: Prepare Railway with the existing unified Dockerfile and explicit dashboard settings; preserve legacy railway.json but do not depend on deprecated config-as-code support for new services.
