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
- 2026-10-24: Demo UI is a no-build React page (React 18 from a CDN, JSX compiled by in-browser Babel) in `frontend/demo`, served with `python -m http.server`. The local Node is 14.17, too old for Vite, and this needs no install.
- 2026-10-24: The demo fakes the group in one browser tab (three scripted friends, scripted votes). No backend or real-time sync yet.
- 2026-10-24: Three candidate looks (Velvet, Neon, Matinee) are CSS token sets switchable from the demo toolbar. Pick one before building the real app.
- 2026-10-24: Only the big screen moves the night forward (start, skip, picks, start movie). Phones join, react and vote, then wait with instructions.
- 2026-10-24: Dropped the per-person "movie vibe" card; each person picks how they want to feel tonight instead, and it shows on their seat.
- 2026-10-24: The night ends on a top 3 (golden buzzers first, then by votes, then by prediction) plus 5 predicted recs.
- 2026-10-24: Progress shows as a "completion status" loading bar in the big screen's top-right, not as a model confidence score.
- 2026-10-24: Votes are private. Screens show who has voted and whether it was unanimous, never who said yes or no (no per-seat reveal, no counts).
- 2026-10-25: Real app = Vite + React + TypeScript in `frontend/` on Node 22 LTS. Velvet is the only look; `frontend/demo` stays as a reference.
- 2026-10-25: First app pass is frontend only: buttons navigate, and screens read typed mock data shaped like the backend's responses through `src/api`. Swapping that module is how the backend gets wired in.
- 2026-10-25: React Router, one URL per screen (`/tv/*`, `/phone/*`), plus a dev-only index of every screen at `/`.
- 2026-10-25: Onboarding on the phone = join → Sign in with Google → tonight's feeling → 3 Instagram Explore screenshots → reading → waiting.
- 2026-10-25: Every 5 trailers without a golden buzzer, the TV offers "See our picks" or "Keep watching". A golden buzzer offers picks or keep browsing.
- 2026-10-25: GSAP (`@gsap/react`) only for the big moments (curtains, golden buzzer, podium, screen changes); CSS for the rest; everything honours reduced motion.
- 2026-10-25: Posters and trailers stay generated art / placeholders until the backend is wired; then TMDB by `tmdb_id`.
- 2026-10-25: Deferred to backend wiring: an in-memory sessions module (FastAPI + WebSockets) that runs the night; dev login locally, Google on the hosted server; re-rank group recs after every vote, excluding films already shown; each feeling maps to catalog tags and everyone's are blended into one boost list.
