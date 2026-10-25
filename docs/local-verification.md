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
  original training behavior. Screenshot ingestion needs a working Llama key/provider.
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
  `FRONTEND_ORIGINS`, and, for screenshots, `LLAMA_API_KEY` with the intended provider
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
