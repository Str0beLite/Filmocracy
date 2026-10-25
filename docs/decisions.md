# Decisions

One line each: date, decision, why.

- 2026-10-25: Backend is one FastAPI process (serving + background trainer thread). W is ~6k params, so retraining takes seconds on CPU and needs no separate worker or GPU.
- 2026-10-25: Host on Railway (Dockerfile, volume at `/data` for SQLite + W checkpoints). HF Spaces is the free fallback, but its disk is wiped on restart.
- 2026-10-25: Open-vocabulary tags: every tag string is embedded with frozen `bge-small-en-v1.5` (not an LLM); a feed or film = weighted mean of its tag embeddings. W = I + ABᵀ (384×384, rank 8), so no fixed tag lists or hand-made prior. Replaces the fixed 132-tag × movie-tag W.
- 2026-10-25: Only LLM step is screenshot → free-form tags, using Meta Llama vision (Llama API, OpenAI-compatible) [replaced, see below]. No LLM on the movie side.
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
- 2026-10-25: Vision moves from Llama to Meta Muse Spark (`muse-spark-1.3`, Meta Model API). Explore screenshots are split into tiles by pixel colour (`grid.py`) and each tile is read on its own; Muse's 4M tokens/min limit makes per-tile calls practical.
- 2026-10-25: Muse prompt asks for personality traits phrased like film tags, not post contents; reasoning effort `minimal` (same tags as `low` in testing, ~40% faster per tile). After the per-tile reads, one text-only Muse call (`vision.summarize`) sums the whole feed up into 10–15 tags; plain averaging is the fallback. Tags-only beat also sending the screenshots.
- 2026-10-25: Dev-only `GET /dev/feeds/{fid}/top` (TANDEM_DEV_AUTH=1) + `scripts/vision_demo.html` for testing screenshots → tags → top 5, scored with untrained W = I plus a 0.05 × popularity-percentile² nudge.
