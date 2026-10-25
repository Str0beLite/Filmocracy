# Local verification and Railway handoff

Verified 2026-10-25. Active entry point: `unified:app` (`backend/app.py` is an alias).
Docker and `backend/railway.json` already select that entry point. No deployment,
push, schema change, catalog replacement or model training was performed for this review.

## Migration findings

- Runtime storage: SQLite `tandem.db`; 5,000 canonical MovieLens rows and 200
  supplementary metadata records. A read-only check of the existing local database
  returned `integrity_check=ok`, with no foreign-key errors.
- No active Supabase SDK, authentication, database RPC or realtime dependency found.
  Historical migrations/guides and local environment templates still mention Supabase.
  Local configuration files were left untouched.
- Google verifies identities; SQLite stores application profiles, feeds, memberships,
  invitations, rounds, votes, queues, predictions and feedback. SQLite itself is not
  an authentication provider. Real Google browser sign-in was not exercised here.
- Durable `/sessions` provides the movie-night workflow. The legacy `/groups` preview
  API still stores its group registry in memory and loses it on restart; this is an
  exception to the claim that *all* application state is persistent. Use `/sessions`
  for the TV/phone workflow. Migrating the separate preview API was outside this change.
- Unified deliberately disables retraining. Votes synchronize to recommendation
  feedback without updating the model; the standalone recommendation app retains its
  original training behavior. Screenshot ingestion needs a working Muse Spark key/provider.
- The catalog has 5,000 movies, but trailer queues use only mapped metadata with
  provider-verified playable trailers, not every catalog movie. No catalog expansion.

## Results

The backend suite passes 27 tests, including simultaneous voting, atomic advancement,
invitation rotation, ownership enforcement, disconnection leases, skip/end, ranking,
feedback failure recovery, restart persistence, SSE and WebSocket synchronization.
The frontend helper passes 4 tests, including authenticated WebSocket setup and stale
snapshot filtering. Test databases and synthetic training checkpoints are temporary.

A separate Uvicorn process was also run with an isolated temporary SQLite database,
the real configured `BAAI/bge-small-en-v1.5` encoder, existing seed checkpoint, full
5,000-movie catalog and locally configured YouTube key. Google authentication used
explicit local `TANDEM_DEV_AUTH=1`, not real sign-in. Verified:

1. Create a TV session; create feeds and join three phone identities.
2. Reject missing authentication and unrelated-session access.
3. Prepare 10 recommendations using real trailer verification.
4. Submit three simultaneous votes in each of two rounds: exactly one advancement
   per round, with six persisted votes total.
5. Place a unanimously approved movie above a mixed-vote movie in final rankings.
6. Receive WebSocket state updates and synchronize after reconnecting.
7. Terminate and restart the entire backend process on the same SQLite directory;
   votes, movie queue and round records are unchanged and the socket reconnects.
8. Skip with a round identifier, retry without duplicate advancement, and end session.

The verification process was stopped afterward. The real application database was
not used for these workflow writes. No recommendation model was trained or overwritten.
The frozen encoder download is cached under ignored `backend/data/hf-cache`.

## Docker verification: passed

Docker Desktop is now installed and its engine is running. Its CLI/credential helper
were absent from the shell PATH; the build succeeded after using:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
docker build -t tandem-local-check:20261025 backend
```

Verified the actual Linux ARM64 image on this Apple Silicon machine:

- Image build completed with the real frozen encoder baked in.
- All 27 backend tests passed inside the image (read-only test fixtures, temporary
  databases, no local configuration files mounted).
- The container ran the complete TV/three-phone workflow: real trailer checks,
  10 queued movies, six votes across two rounds, simultaneous voting, exactly-once
  advancement, unanimous-before-mixed rankings, WebSocket updates/reconnect, skip/end.
- Startup succeeded with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, confirming
  the baked encoder is sufficient at runtime.
- Both stop/start and removing/recreating the container with the same named `/data`
  volume preserved votes, queued movies and round history.
- The image contains no `.env*` files or preloaded runtime SQLite database.
- Disposable test containers and their own named volumes were removed. The built
  `tandem-local-check:20261025` image remains available locally.

Image digest: `sha256:436dce25553a98173058eb8139d6a3558c12284265d437b79466b8dbdd4ec198`.
No Dockerfile changes were required. Real Google sign-in still needs browser testing;
workflow checks used isolated local development identities. Linux AMD64 and actual
Railway deployment/restart were not tested. No deployment or push was performed.

To repeat manually with Docker running, from the repository root:

```bash
docker build -t tandem-local backend
docker volume create tandem-local-check
docker run --name tandem-local-check --rm -p 8000:8000 \
  --mount source=tandem-local-check,target=/data \
  -e TANDEM_DEV_AUTH=1 -e TANDEM_DATA_DIR=/data \
  -e YOUTUBE_API_KEY -e FRONTEND_ORIGINS=http://localhost:5173 tandem-local
```

Export the trailer key locally before running; do not put it in shell history, a
Dockerfile or a tracked env file. This is a disposable local-development container.
Check `/ready` for `sqlite_movies: 5000`, repeat the workflow with local bearer names,
then stop and run the same command against the same named volume to verify persistence.
Do not remove the volume between runs. Do not use development auth on Railway.
The image build downloads CPU PyTorch dependencies and the frozen encoder; network
access and sufficient disk space are required.

## Railway requirements before deployment

- Set service root to `backend`, using its Dockerfile and `railway.json`.
- Attach an actual persistent Railway volume at `/data`, and set
  `TANDEM_DATA_DIR=/data`. The manifest requires this mount; it does not create the
  volume. Railway supplies `RAILWAY_VOLUME_MOUNT_PATH` automatically. Startup rejects
  a missing/wrong mount. Volume data is available at runtime, not during image build.
- Keep one service instance and one Uvicorn worker. Session authorization and atomic
  writes use SQLite transactions; the legacy group registry and connection lifecycle
  are process-local. Railway volume services do not support replicas.
- Configure `GOOGLE_CLIENT_ID`, `YOUTUBE_API_KEY`, exact comma-separated
  `FRONTEND_ORIGINS`, and, for screenshots, `MUSE_API_KEY` with the intended provider
  URL/model. Never enable `TANDEM_DEV_AUTH` or `TANDEM_FAKE_ENCODER` in deployment.
  No Supabase credentials are required.
- Use `wss://` for phone/TV connections and the frontend Google OAuth client matching
  the backend. Include the frontend's exact HTTPS origin in the WebSocket allowlist.
- `/ready` checks SQLite/catalog readiness, not successful Google sign-in, YouTube
  quota, screenshot-provider credentials or browser trailer playback. Test those
  separately after a future approved deployment.
- Keep SQLite, its WAL/SHM files and any model checkpoints together under `/data`.
  Do not upload/copy a live `tandem.db` alone; use a consistent SQLite backup or stop
  the writer before copying. Enable volume backups and test restoration.
- A fresh volume initializes from the committed catalog/metadata and existing seed
  checkpoint; it does not automatically include developer-created users or sessions.
  Importing existing local runtime data requires a separate approved transfer.
- Test an actual Railway redeploy/restart and WebSocket reconnect before calling
  production persistence verified. Deployments will disconnect sockets; clients must
  reconnect with a fresh token and apply the returned complete snapshot.

Official references: [volume setup](https://docs.railway.com/volumes),
[volume limits](https://docs.railway.com/volumes/reference),
[backups](https://docs.railway.com/volumes/backups).

See the [Railway production handoff](railway-deployment.md) for current dashboard settings, production variables, approval boundaries and the post-deployment checklist.

Release preparation also verified a Railway-style `PORT=8123` in Docker: PID 1 used `unified:app --port 8123 --workers 1`, SQLite resolved to `/data/tandem.db`, readiness reported 5,000 movies with training disabled, and unauthenticated session creation returned 401. Separate containers rejected a missing mount and `TANDEM_DEV_AUTH=1`. These were disposable local simulations, not Railway deployments.

## Muse Spark re-verification (2026-10-25)

Selectively integrated upstream `4b41190` on `codex/railway-deployment-prep`, retaining
unified identity injection, tag validation, SQLite storage, WebSockets and deployment
settings. The recommendation model/scoring, existing catalog files, checkpoints and
SQLite schema are unchanged. Integration changes were reviewed before the approved local commit; publication and deployment remain separate approvals.

- Local backend: **37 passed**. Rebuilt Docker backend: **37 passed**. These include
  11 upstream pipeline tests, 3 upstream tiling tests, 12 unified session tests,
  4 idempotent metadata/import tests, and 7 new Muse contract/upload/error tests.
- Frontend session helper: **4 passed**. Scoped lint and wheel/sdist build passed;
  the wheel includes `tandem/grid.py` and declares Pillow as a runtime dependency.
- Image: `tandem-muse-check:20261025` (Linux ARM64), digest
  `sha256:0ebfb534b0e43f13450d6c8d6ff6d8e661ce340c89931f6da007ad75bf772266`.
  Existing Dockerfile installs Pillow through updated `requirements.txt`.
- Isolated real-container workflow passed: 10 verified-trailer queue entries,
  three simultaneous voters, six votes over two rounds, exactly-once advancement,
  unanimous-before-mixed ranking, WebSocket delivery/reconnect, skip/end, and volume
  persistence across container replacement. Encoder and recommendation checkpoint
  were the actual bundled configuration; sign-in used local development identities.
- Empty-volume verification passed again: automatic creation of all 18 tables,
  5,000 unique movies retrieved across all 10 API pages, 200 supplementary metadata
  records, bundled files matching the repository, 5,000-by-384 model vectors and
  10 recommendations from the pipeline. Every table's contents remained identical
  across recreation, including four profiles, three votes and deliberately edited
  test movie/metadata records. Integrity was `ok`, with no foreign-key errors.
- The original local `backend/data/tandem.db*` file hashes were unchanged. Disposable
  workflow containers/volumes were removed; images remain available locally.
- A real SDK mock-transport test verifies the unified upload splits a six-tile
  image and sends image data URLs, JSON schema, `low` reasoning and 4096-token budget
  to the configured Muse endpoint. Provider failures yield 503 with no partial feed.
- **Live Muse inference remains unverified:** no `MUSE_API_KEY` or `MODEL_API_KEY`
  was configured in the local process or standard backend environment files.
  No personal screenshot was sent to Muse. Primary provider documentation was checked;
  see [the request contract and production variables](railway-deployment.md#muse-spark-integration).

Environment templates contain placeholders only; a real key encountered in a local
example was privately preserved and removed from the template. Existing ignored
credential files were not changed. No push, branch merge or deployment was performed during this integration.

## Live Muse verification (2026-10-25)

After configuring `MUSE_API_KEY` in ignored `backend/.env.test`, one real request
through `vision.read_screenshots` succeeded against Meta's API using
`muse-spark-1.3`, low reasoning and the application JSON schema/token budget.
A small synthetic image produced 11 parsed tags and was not classified as noise.
No retries, personal screenshots, database writes or model training were involved;
API credentials and image contents were not logged. This supersedes the earlier
missing-credential limitation for live inference. Actual Instagram screenshot
quality and Railway/provider load remain acceptance checks.

## watchtandem.tech production preparation (2026-10-25)

- Finished the main update through `89a01f0` on the deployment branch. Main's new
  personality prompt, minimal reasoning, whole-feed summary/fallback and dev-only
  vision preview are retained; unified auth/session protections remain intact.
- Final native backend suite: **42 passed**. Final Docker backend suite: **42 passed**.
  The added production tests cover the exact `https://watchtandem.tech` CORS origin,
  HTTP/socket Google-verifier client-ID wiring and ownership, and refusing fake
  encoding on Railway. Google signature verification is a test double in those
  tests; they are not real GIS browser sign-in evidence.
- **4 frontend helper tests passed**. No complete frontend is in the current/local
  branches. Remote `app` (`fcaaa14`) has the teammate's Vite UI draft, still using
  a mock API, fake sign-in and dev-server SSE. Per instruction, it was inspected
  read-only and frontend work/builds are deferred until the teammate finishes it.
- Docker image `tandem-watchtandem-check:20261025` built successfully (Linux ARM64).
  Digest: `sha256:6a8f0390bf742155660138c5ad402f34aef191b88c2e744168227f0a03844c79`.
- A new empty persistent volume created all 18 tables and all 5,000 canonical movies.
  All 10 API pages were retrieved with 5,000 unique IDs. Full table hashes matched
  across container replacement, including test profiles/votes and deliberate test
  metadata edits. Existing local SQLite files were unchanged; disposable resources
  were removed. The bundled catalog and checkpoint were not changed or trained.
- Local HTTPS/WSS verification used an ephemeral self-signed certificate explicitly
  trusted by the test client (certificate checking stayed enabled). The app accepted
  browser origin `https://watchtandem.tech`, rejected an unrelated socket origin,
  delivered three simultaneous votes with exactly one advancement, and synchronized
  after WSS reconnection. The test listened on PORT 8123. Identities were local dev
  identities; this was not a public DNS/certificate or real Google-login test.
- The isolated session workflow used live YouTube trailer verification successfully.
  Live Muse's current minimal-reasoning flow also passed: two synthetic-image
  requests, one text-only summary, 11 parsed summary tags, zero dropped images. No
  retries, actual screenshots, credentials or image contents were logged. Real
  Instagram interpretation and production account quota still need acceptance.

Railway resources, Cloudflare Pages/DNS, public certificates and Google console
settings have not been changed. Follow [production-deployment.md](production-deployment.md)
for the exact manual configuration and outstanding acceptance checklist.
