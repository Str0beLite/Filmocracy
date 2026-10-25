> **watchtandem.tech deployment:** See [the production guide](production-deployment.md) for Railway, Cloudflare Pages, custom domains, Google configuration and the frontend completion blocker.

# Railway deployment handoff

Prepared 2026-10-25. Nothing has been pushed or deployed. Use the existing Dockerfile;
no recommendation changes, model retraining, catalog imports or database transfer are
part of this handoff. See [local verification](local-verification.md) for Docker and
SQLite persistence evidence and [API integration](unified-backend.md) for the wire protocol.

## Approval boundary

Local commits are authorized. The following remain pending explicit approval:

- Push the reviewed branch/commits to GitHub; merge into a remote deployment branch
  only if separately approved. A push to a connected branch can trigger a deployment.
- Create or change Railway services, attach paid persistent storage, add production
  credentials, generate a public domain, or deploy the backend.
- Change Google OAuth production settings or publish/change the frontend configuration.
- Transfer any existing runtime database, delete/reset a volume, expand the movie
  catalog, change a schema or train/update a model. None is needed for a fresh deployment.

Configure an empty service before connecting a live GitHub source, or disable automatic
deployments first. Do not approve a combined push/deploy accidentally by enabling
GitHub autodeploys before the release has been reviewed.

## Exact service settings

For a new Railway service, set these in its dashboard after approval:

| Setting | Value |
| --- | --- |
| Source | `Str0beLite/tandem`, explicitly approved remote branch/commit |
| Root directory | `/backend` |
| Builder | Dockerfile; existing `backend/Dockerfile` becomes `Dockerfile` in this context |
| Custom build command | None; let the Dockerfile build the image |
| Start command | `sh -c 'exec uvicorn unified:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1'` |
| Health check | `/ready`, timeout 120 seconds |
| Replicas/regions | One replica in one region |
| Restart policy | On failure |
| Serverless/sleep | Disabled |
| Persistent volume | Attach a real volume to this service, mount at `/data` |
| Public networking | Generate an HTTPS domain; target Railway's assigned `PORT` |

The Dockerfile already uses this same start command. `backend/app.py` is only an alias
for `unified:app`; do not start `tandem.api:app`, which bypasses durable session endpoints
and uses the standalone training behavior. The shell expands Railway's assigned `PORT`;
8000 is only the local fallback. One Uvicorn worker plus one service replica keeps
background jobs and connection state in one process.

**Configuration-file compatibility:** Railway's current documentation deprecates
`railway.json`/`railway.toml`, says new services cannot opt in, and gives 2026-12-01 as
the legacy cutoff. Keep `backend/railway.json` as the existing settings reference; do
not assume a new service will load it. Use the dashboard settings above for this
hackathon deployment. For an existing legacy service that still supports the file,
its explicit config path is `/backend/railway.json`, independent of the root directory.
The file already specifies one replica, required `/data` mount, `/ready`, no sleep and
the unified start command. A future IaC conversion is separate from this deployment.

Sources: [config compatibility](https://docs.railway.com/config-as-code),
[monorepo paths](https://docs.railway.com/deployments/monorepo),
[Dockerfile builds](https://docs.railway.com/builds/dockerfiles).

## Production variables

Enter secret values directly in Railway Variables. Do not commit or upload local env
files. Values below are placeholders/settings, never actual credentials.

| Variable | Production value/purpose |
| --- | --- |
| `TANDEM_DATA_DIR` | `/data` (also the Docker image default) |
| `GOOGLE_CLIENT_ID` | Google **Web application** OAuth client ID; same public ID as frontend GIS |
| `YOUTUBE_API_KEY` | Server-only Google Cloud key with YouTube Data API v3 enabled; validates trailers |
| `FRONTEND_ORIGINS` | Exact frontend HTTPS origins, comma-separated, e.g. `https://your-frontend.example`; no paths, trailing slashes or wildcard |
| `TANDEM_DEV_AUTH` | `0` (or unset); never `1` in production |
| `TANDEM_FAKE_ENCODER` | `0` (or unset); use the real frozen encoder |
| `SWEEP_ENABLED` | `true` (default); expires disconnected participants |
| `TRAILER_REGION` | Audience region, default `US` |
| `MUSE_API_KEY` | Server-only provider key, required for Instagram screenshot onboarding; tags-only feeds work without it |
| `MUSE_BASE_URL` | Intended OpenAI-compatible vision provider endpoint; default `https://api.meta.ai/v1` |
| `MUSE_MODEL` | Default `muse-spark-1.3` on Meta Model API |
| `MUSE_REASONING` | Default `minimal`; empty omits the parameter. Meta supports minimal/low/medium/high/xhigh/max; `none` is rejected |
| `MUSE_MAX_TOKENS` | Default `4096`; includes internal reasoning and visible JSON output |

Railway supplies `PORT`, `RAILWAY_ENVIRONMENT_ID`, and the volume's
`RAILWAY_VOLUME_MOUNT_PATH`; do not invent these to bypass startup checks. Leave
`TANDEM_CATALOG_DIR`, `TANDEM_SEED_W` and `HF_HOME` at image defaults. Do not set an
admin token to enable training: unified disables both the training worker and retrain
endpoint by design. No Supabase, TMDB import, database URL or Google client secret is
required for this deployment. Provider keys belong only in the backend; public frontend
configuration should contain the API URL and Google client ID, not backend secrets.

## SQLite persistence and backups

The SQLite path is `/data/tandem.db`; existing model checkpoints also belong under
`/data/checkpoints`. The volume must be attached, not merely an environment variable.
Railway mounts it at runtime, so do not put SQLite migrations in a pre-deploy command.
Startup applies the existing additive schema and loads the unchanged catalog snapshot;
a fresh volume gets 5,000 canonical movies plus 200 metadata records, without developer
sessions/accounts. This does not transfer or overwrite an existing runtime database.

The app refuses Railway startup when the mount/data path is wrong or development auth
is enabled. `BEGIN IMMEDIATE`, a connection lock, uniqueness constraints and WAL mode
protect voting transactions; they are not a reason to add workers or replicas.

Enable scheduled volume backups and verify restore procedures before relying on
production data. Back up the database consistently with SQLite's backup API or while
the writer is stopped; copying a live `tandem.db` alone can omit WAL data. Never wipe a
volume to fix an application error. Legacy `/groups` previews remain in memory and
are not restart-persistent; use `/sessions` for the durable phone/TV workflow.

Sources: [volume setup](https://docs.railway.com/volumes),
[volume constraints](https://docs.railway.com/volumes/reference),
[backups](https://docs.railway.com/volumes/backups).

## Frontend HTTP and WebSocket URLs

The actual hostname cannot be known until Railway generates it. For the assigned
`<backend-domain>` (often `*.up.railway.app`):

| Purpose | URL |
| --- | --- |
| API base, pass as helper `apiUrl` | `https://<backend-domain>` |
| Readiness | `https://<backend-domain>/ready` |
| Interactive HTTP docs | `https://<backend-domain>/docs` |
| HTTP OpenAPI | `https://<backend-domain>/openapi.json` |
| Session WebSocket | `wss://<backend-domain>/sessions/<session-uuid>/ws` |

There is no `/api` prefix and no public `:8000` port. Use the same backend domain for
HTTP and WebSockets; no second socket service or port is needed. If the frontend is
Vite, `VITE_API_URL=https://<backend-domain>` is the intended build-time setting;
the current frontend folder is a helper, not a finished UI, so its agents must wire
that setting into `createTvSessionClient` and `connectSession`. Use the same public
Google client ID (conventionally `VITE_GOOGLE_CLIENT_ID`) in the sign-in UI.

On WebSocket open, send `{"type":"auth","token":"<fresh Google ID token>"}` within
10 seconds. Receive full `state` snapshots, send `heartbeat` every 10 seconds, and
reconnect with backoff/fresh credentials after network or deployment interruptions.
`connectSession` handles authentication, heartbeats and stale snapshots; its `onClose`
callback must implement the UI's reconnect/sign-in flow. Mutations still use HTTP
with `Authorization: Bearer <Google ID token>`. Never put a token in a socket URL.

Railway supports WebSockets on its public HTTP service:
[WebSocket deployment guide](https://docs.railway.com/guides/sse-vs-websockets).

## Post-deployment acceptance checklist

These checks are pending deployment approval and must use unique test sessions and
accounts; delete only records that the test itself creates, if cleanup is needed.

- [ ] Confirm build uses the existing Dockerfile and logs show `unified:app`, one
  worker, no trainer worker, and the assigned port. Check the volume is really `/data`.
- [ ] Confirm `/ready` reports `database: sqlite`, `movies: 5000`, `sqlite_movies: 5000`,
  and `training_enabled: false`. Readiness does not validate external credentials.
- [ ] Set the frontend's HTTPS origin in both Google OAuth Authorized JavaScript origins
  and `FRONTEND_ORIGINS`; ensure consent/testing status permits all team test accounts.
  This is Google Identity Services ID-token sign-in, not a Supabase login or OAuth
  backend callback. Do not add a backend redirect URI unless the frontend uses such a flow.
- [ ] Sign in through the real frontend, call `/me`, and confirm the correct Google `sub`.
  Missing, invalid, expired or wrong-client tokens must be rejected. Token refresh /
  renewed Google sign-in must restore access; no development bearer-name bypass.
- [ ] Test actual Muse Spark onboarding: Explore tiles become separate image calls, plain images remain whole, and ads/noise are excluded. Verify provider quota and nonempty JSON tags; then create
  feeds for three phones. Real provider API/key/quota checks are not covered by `/ready`.
- [ ] Use one TV host plus **three distinct Google accounts** on phones (same Google
  account on multiple devices is one voter). Create a session, scan its QR on each
  phone, join and connect all clients to the same session UUID over `wss://`.
- [ ] Verify real trailer playback on the TV, plus region/age/embed restrictions; a
  successful YouTube API response alone does not guarantee browser playback.
- [ ] Vote simultaneously on all three phones. TV receives the new snapshot within
  roughly a second and sees exactly one advancement; duplicate/stale votes do not
  create another round. Repeat with mixed votes and verify unanimous results rank first.
- [ ] Disconnect one phone. Its 45-second lease plus the sweep interval (up to about
  10 more seconds) prevents indefinite blocking. Reconnect and synchronize current state.
- [ ] Refresh the TV and retain its session UUID/host identity; show a rotated QR if
  needed. Test host skip, duplicate skip with the same round ID, and session termination.
- [ ] An unrelated signed-in user cannot read the session or open its socket; bad
  browser origins fail the socket handshake and other users cannot submit host controls.
- [ ] Redeploy/restart on the same volume: existing votes/rounds/queues remain, and
  phones/TV reconnect with refreshed tokens and consistent full snapshots.
- [ ] Confirm backups are enabled and logs contain no tokens/provider secrets. Keep
  a separate approval boundary for any restore or existing database transfer.

No real Google sign-in, Railway volume restart, Linux AMD64 container run or public
phone-to-TV test has been performed yet. Local Linux ARM64 Docker tests passed; those
results are preparation evidence, not a claim that the public deployment is verified.

## Muse Spark integration

Upstream `4b41190` is selectively integrated into unified screenshot uploads; keep the
existing authenticated routes, SQLite schema/catalog, WebSocket protocol and disabled
trainer. Install `pillow>=10` (included in both package and Docker requirements). Old
`LLAMA_*` names are no longer read. Rename credentials in Railway to `MUSE_API_KEY`;
a credential named `MODEL_API_KEY` in Meta examples must be assigned to this app's
`MUSE_API_KEY`. A fresh Muse key is not automatically a valid legacy Llama key.

Contract checked against Meta's primary docs: OpenAI-compatible
`POST https://api.meta.ai/v1/chat/completions`, `muse-spark-1.3`, image data URLs in
`user` message `image_url.url`, `response_format.json_schema`, top-level
`reasoning_effort=low`, and `max_tokens=4096`. Parse
`choices[0].message.content` as JSON, tolerate fenced JSON and treat unreadable
answers as noise. Provider API failures return a retryable 503 without creating a
partial feed. No key or image content is included in the application error response.

Sources: [Chat Completions](https://dev.meta.ai/docs/protocols/chat-completions),
[image understanding](https://dev.meta.ai/docs/image-understanding),
[structured output](https://dev.meta.ai/docs/structured-output),
[reasoning](https://dev.meta.ai/docs/reasoning).

Live Muse verification passed on 2026-10-25 after the key was configured locally:
one synthetic-image request through the application vision function succeeded with
`muse-spark-1.3`, `reasoning_effort=low`, the JSON schema and configured token budget.
The response parsed into 11 tags and was not marked as noise. Retries were disabled;
neither the key nor image contents were logged. This verifies endpoint/model access
and the request/response contract. Real Instagram screenshot quality, production
quota/load and Railway connectivity still require post-deployment checks.

Main update `89a01f0` changes the default to minimal reasoning and adds one text-only whole-feed summary after tile reads. Failed summaries fall back to the plain average. The current minimal-reasoning flow passed a live synthetic-image and whole-feed summary probe; real Instagram quality still needs acceptance. The `/dev/feeds/{id}/top` preview and vision demo are development-only; production Railway keeps development auth disabled.
