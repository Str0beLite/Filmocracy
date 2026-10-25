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

- 2026-10-24: Integration branch retains every upstream recommendation endpoint and Google-auth standalone mode; unified production injects Supabase JWT identities, keeps durable session voting and disabled training, and leaves legacy /groups ephemeral. Google GIS clients exchange their ID token through Supabase Auth before calling unified endpoints.

- 2026-10-24: User requested all Supabase functionality move to main's SQLite database; retain Google auth/MovieLens identities, additive transactional session tables, authenticated SSE instead of Supabase Realtime, all 200 source movie records and unchanged remote data/model checkpoints.
- 2026-10-25: Vision moves from Llama to Meta Muse Spark (`muse-spark-1.3`, Meta Model API). Explore screenshots are split into tiles by pixel colour (`grid.py`) and each tile is read on its own; Muse's 4M tokens/min limit makes per-tile calls practical.
- 2026-10-25: Muse prompt asks for personality traits phrased like film tags, not post contents; reasoning effort `minimal` (same tags as `low` in testing, ~40% faster per tile). After the per-tile reads, one text-only Muse call (`vision.summarize`) sums the whole feed up into 10–15 tags; plain averaging is the fallback. Tags-only beat also sending the screenshots.
- 2026-10-25: Dev-only `GET /dev/feeds/{fid}/top` (TANDEM_DEV_AUTH=1) + `scripts/vision_demo.html` for testing screenshots → tags → top 5, scored with untrained W = I plus a 0.05 × popularity-percentile² nudge.
- 2026-10-24: Demo UI is a no-build React page (React 18 from a CDN, JSX compiled by in-browser Babel) in `frontend/demo`, served with `python -m http.server`. The local Node is 14.17, too old for Vite, and this needs no install.
- 2026-10-24: The demo fakes the group in one browser tab (three scripted friends, scripted votes). No backend or real-time sync yet.
- 2026-10-24: Three candidate looks (Velvet, Neon, Matinee) are CSS token sets switchable from the demo toolbar. Pick one before building the real app.
- 2026-10-24: Only the big screen moves the night forward (start, skip, picks, start movie). Phones join, react and vote, then wait with instructions.
- 2026-10-24: Dropped the per-person "movie vibe" card; each person picks how they want to feel tonight instead, and it shows on their seat.
- 2026-10-24: The night ends on a top 3 (golden buzzers first, then by votes, then by prediction) plus 5 predicted recs.
- 2026-10-24: Progress shows as a "completion status" loading bar in the big screen's top-right, not as a model confidence score.
- 2026-10-24: Votes are private. Screens show who has voted and whether it was unanimous, never who said yes or no (no per-seat reveal, no counts).
- 2026-10-25: Real app = Vite + React + TypeScript in `frontend/` on Node 24 LTS (winget's current LTS). Velvet is the only look; `frontend/demo` stays as a reference.
- 2026-10-25: First app pass is frontend only: buttons navigate, and screens read typed mock data shaped like the backend's responses through `src/api`. Swapping that module is how the backend gets wired in.
- 2026-10-25: Replaced the per-screen mock with a fake backend inside the Vite dev server (`frontend/mock-backend/`): one in-memory room, actions over POST, live snapshots over Server-Sent Events. Lets the team test the real multi-phone experience with no Python service. The real session service should keep the same snapshot/actions protocol.
- 2026-10-25: Devices follow the room: each frame navigates to the screen the room's state implies, so the URL always names the screen. Phones are identified per browser tab (sessionStorage); the name step stands in for Google sign-in.
- 2026-10-25: React Router, one URL per screen (`/tv/*`, `/phone/*`), plus a dev-only index of every screen at `/`.
- 2026-10-25: Onboarding on the phone = join → Sign in with Google → tonight's feeling → 3 Instagram Explore screenshots → reading → waiting.
- 2026-10-25: Every 5 trailers without a golden buzzer, the TV offers "See our picks" or "Keep watching". A golden buzzer offers picks or keep browsing.
- 2026-10-25: GSAP (`@gsap/react`) only for the big moments (curtains, golden buzzer, podium, screen changes); CSS for the rest; everything honours reduced motion.
- 2026-10-25: Posters and trailers stay generated art / placeholders until the backend is wired; then TMDB by `tmdb_id`.
- 2026-10-25: Deferred to backend wiring: an in-memory sessions module (FastAPI + WebSockets) that runs the night; dev login locally, Google on the hosted server; re-rank group recs after every vote, excluding films already shown; each feeling maps to catalog tags and everyone's are blended into one boost list.
- 2026-10-25: Trailers come from TMDB (`/movie/{tmdb_id}/videos`, official YouTube trailer first), not MovieLens's `ml-20m-youtube` file: that file stops around 2015 and many of its links are dead. The TV plays it in a youtube-nocookie embed; no token or no trailer falls back to placeholder art.
- 2026-10-25: A real trailer plays to its end. The TV listens to the YouTube embed (postMessage): when it starts playing it tells the room the video's length (`trailerPlaying`, so phones show the right clock), and when it ends it opens voting. The room keeps a backstop timer 5 s past the end; placeholder trailers stay 12 s.
- 2026-10-25: A feed's votes pull its next recs toward loved films right away (Rocchio on the predicted taste, serving only), so a session reacts before W retrains.
- 2026-10-25: Popularity is one learned weight on a rank-percentile prior next to W, not something W has to encode; it starts at 0.05.

- 2026-10-25: Use authenticated WebSockets for phone/TV session snapshots and heartbeats; retain HTTP mutation transactions and SSE compatibility, with SQLite revisions providing reconnect synchronization.
- 2026-10-25: Prepare Railway with the existing unified Dockerfile and explicit dashboard settings; preserve legacy railway.json but do not depend on deprecated config-as-code support for new services.

- 2026-10-25: Selectively integrate upstream 4b41190: Muse Spark via Meta Model API and pixel-based Explore tiling; retain unified Google authentication, SQLite transactions, WebSockets and disabled model training.

- 2026-10-25: Merge main 89a01f0 into deployment preparation, retaining personality-first tags and whole-feed summary/fallback, minimal reasoning and the dev-only preview alongside unified authentication, SQLite sessions and WebSockets.

- 2026-10-25: Prepare watchtandem.tech for Cloudflare Pages and api.watchtandem.tech for Railway with exact-origin CORS, GIS ID tokens and a persistent /data volume; wait for the teammate app branch to replace its mock API before frontend deployment.
- 2026-10-25: The frontend runs on the real session backend (mock backend removed). The TV hosts and runs the night's choreography, publishing it as a host-only session `stage`; phones follow over the WebSocket. Added `stage`, `feeling` and `react` endpoints so reactions, shared pause, verdicts, checkpoints and picks keep working. Dev uses the backend's dev login; production uses Google Identity Services.
- Self-host option: Cloudflare Tunnel from a local machine to api.filmocracy.party (docs/self-hosting.md).
- 2026-10-25: Renamed the product to Filmocracy; frontend at filmocracy.party (Cloudflare Pages), API at api.filmocracy.party. Internal identifiers (tandem package, TANDEM_* env vars, storage keys) unchanged.
- 2026-10-25: Dropped Google sign-in for a random user id per browser (bearer token, format-checked only). Backend self-hosted via Cloudflare Tunnel; a systemd timer pulls main every minute instead of a GitHub runner (public repo).

- 2026-10-25: Add individual /training onboarding with exactly three screenshots and verified trailer feedback, using existing SQLite feeds/events/recs and opt-in TANDEM_TRAINING_ENABLED; keep the model algorithm and committed seed unchanged and expose FastAPI through a laptop Cloudflare Tunnel.

- 2026-10-25: Remove Google sign-in from the frontend; per-tab 256-bit guest bearer keys map to separate hashed public user IDs, preserving ownership and WebSocket authorization without schema changes or relinking existing Google profiles.

- 2026-10-25: Integrate the local individual trainer with Filmocracy main cdfc83a, retaining self-hosting, persistent browser IDs and optional YouTube verification; route both direct feedback and synced session votes to the opt-in existing trainer, preserving prior guest identities and catalog/checkpoint data.
- 2026-10-25: /training renders the app's onboarding screens (name, feeling, screenshots, reading) from shared components in `frontend/src/phone/onboarding.tsx`, so the two can't drift; only its header and the trailer/vote loop are its own.
- 2026-10-25: Beta: Pages serves the `dev` branch at beta.filmocracy.party (custom domain on the branch alias); it uses the same production backend, which allows that origin.
- 2026-10-25: Cap the learned popularity weight at `TANDEM_POP_MAX` (default 0). Live training had raised it to 0.30, and 67% of top-10 recs came from the 20% most-rated films (1% from the less-rated half); capped, it is 20% and 20%. A negative cap leans niche.
