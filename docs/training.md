# Individual training on a self-hosted laptop

Open `/training`: First name → feeling → **exactly 3 Explore
screenshots** → trailers and private yes/no votes. Each image must be JPEG, PNG
or WebP, up to 10 MiB. No TV, room or invitation is required. The page uses the
existing Velvet design, browser identity, Muse tiling, recommender and feedback format.

## Run the backend

Use the existing Python environment and an ignored `backend/.env` file:

```ini
TANDEM_DATA_DIR=/absolute/path/to/tandem-runtime
TANDEM_TRAINING_ENABLED=1
TANDEM_RETRAIN_EVERY=20
TANDEM_DEV_AUTH=0
TANDEM_FAKE_ENCODER=0
MUSE_API_KEY=<server-only key>
YOUTUBE_API_KEY=<optional server-only key>
FRONTEND_ORIGINS=https://filmocracy.party,http://localhost:5173
```

Choose the existing runtime directory to retain its records, or a new empty
one for independent training data. Startup creates missing tables and seeds the
same 5,000-movie catalog without overwriting existing rows. Do not run separate
backend processes against the same SQLite/checkpoint directory.

From `backend/`, run:

```sh
.venv/bin/uvicorn unified:app --env-file .env --host 127.0.0.1 --port 8000 --workers 1
```

The existing trainer wakes after 20 feedback events by default. Its algorithm,
holdout checks and acceptance gate are unchanged. Only accepted updates replace
the serving model. New checkpoints go under `TANDEM_DATA_DIR/checkpoints`; the
committed seed and catalog stay unchanged. Accepted models load on restart.
Stored votes survive restarts, although the existing trainer's in-memory
notification counter resets. Use one worker, and back up the database together
with its checkpoints.

Training defaults to off. Set `TANDEM_TRAINING_ENABLED=1` before starting this
training server. `/ready` reports `training_enabled`; authenticated `/model`
shows completed training rounds. Public `/admin/retrain` stays blocked in unified
mode. The page saves feedback even if training is off and displays that status.
A saved vote does not mean a model update has been accepted yet.

Alternatively, use the existing Dockerfile with one container/worker, a persistent
volume at `/data`, `TANDEM_DATA_DIR=/data`, the private environment file and port
8000 published only on `127.0.0.1`. Never commit credentials or runtime data.

## Cloudflare Tunnel

Expose **FastAPI**, not SQLite or a database port. Data stays on the laptop.

1. Make sure `filmocracy.party` is an active Cloudflare DNS zone in your account.
2. In Cloudflare **Networking → Tunnels**, create a named tunnel. Install
   `cloudflared` natively on the laptop using the generated OS-specific commands.
   Keep tunnel credentials outside Git.
3. Add a published application route:
   `api.filmocracy.party` → `http://127.0.0.1:8000`.
   Resolve conflicting `api` DNS records before switching that hostname.
4. Keep the connector and backend running, and the laptop awake and online.
5. Verify `https://api.filmocracy.party/ready` reports 5,000 movies and
   `training_enabled: true`.

A native connector can reach the Docker backend's loopback-published port. A
connector in a separate container cannot use its own `localhost` to reach another
container; use their Docker network address instead.

See [Cloudflare's setup guide](https://developers.cloudflare.com/tunnel/get-started/).
No router port forwarding is required. Keep browser credential authentication active; don't
add a separate interactive Cloudflare Access login unless that browser flow is
also integrated. Keep the API out of blanket cache-everything rules. The tunnel
is not a database backup and cannot keep the laptop online.

## Frontend

Set in the build environment or ignored `frontend/.env.local`:

```ini
VITE_API_URL=https://api.filmocracy.party
```

Run `npm --prefix frontend run dev`, or build with `npm --prefix frontend run build`.
The production host must serve `index.html` for `/training`. No Google configuration
is required. Never put Muse/YouTube/tunnel secrets in Vite variables. Training uses HTTPS requests;
existing movie-night WebSockets continue using WSS with an HTTPS API URL.

## API and persistence

- `POST /profiles/me`: save the caller's display name.
- `POST /training/feeds`: multipart `files` with exactly three images. Returns
  `feed_id`, weighted tags and noise count. Images go to Muse for processing;
  the backend stores the resulting profile, not original screenshots.
- `POST /training/feeds/{feed_id}/next`: JSON `{"boost":["comedy"]}`. Requires
  ownership and returns `rec_id`, `w_version`, and `movie`. Uses the existing
  scorer, popularity prior, vote pull and tag boost. Only existing mapped movies
  with playable catalog trailers are eligible; no catalog import is performed.
- `POST /feedback`: `{"rec_id":123,"label":"love"}` or `"nah"`. Existing
  ownership checks apply. Retrying replaces the feed/movie label instead of
  adding a second training example, and notifies the existing trainer.

Shown films are recorded in `recs` and not repeated for that feed, including
across backend restarts. Skip records no vote. A vote is committed before asking
for the next trailer, so provider failures cannot undo it. Refreshing the page
restarts onboarding; saved profiles, feeds, votes and recommendation history
remain in SQLite. Guest credentials stay in browser storage, survive refreshes, and are not sent in URLs or public snapshots. New visitors keep their identity across visits; per-tab testing uses sessionStorage. Clearing browser storage loses access to that identity. Existing Google-linked data is preserved, not automatically transferred to guests.

The database still has 5,000 movies; the training trailer pool is the smaller
subset with mapped metadata and playable catalog trailers. `409` means that pool
is exhausted, `503` means retry service checks, `401` requires reloading the page to reconnect,
and `403`/`404` protect other users' feeds. Upload errors are `413` (size) or
`422` (count, type or unreadable image).

## Tests

Backend: from `backend/`, run `TANDEM_FAKE_ENCODER=1 .venv/bin/python -m pytest -q`.
Tests use temporary SQLite/checkpoints, synthetic images and mocked providers,
including a real short training run that never writes to the existing database.

Frontend: run build and lint. `frontend/tests/training_browser.py` uses Python
Playwright and Chrome. Start Vite on port 5177, then run
`python frontend/tests/training_browser.py`. Override `TRAINING_TEST_ORIGIN` or
`TRAINING_TEST_CHROME` if necessary. This checks phone and desktop UI using
anonymous credentials and synthetic API boundaries, not live providers.
Real Muse, YouTube playback and the public tunnel need a manual check before
inviting testers. Guest keys are 256-bit random bearer credentials. The backend
hashes them into distinct public IDs so knowing a profile ID cannot grant access.

## Compatibility with the new backend

The trainer is integrated with main's Filmocracy unified app and self-hosting
setup. Both individual `/feedback` calls and synced session votes notify the
existing automatic trainer when `TANDEM_TRAINING_ENABLED=1`. A sync or provider
failure cannot roll back a previously accepted session vote.

The newer backend trusts catalog trailers when `YOUTUBE_API_KEY` is absent. With
a key it additionally verifies embeddability and region availability. Training
uses that same policy; it never expands or overwrites the movie catalog.

Existing `phone-...`/`tv-...` browser identities from main remain supported. New
training guest keys get separate hashed public IDs. Previously issued per-tab
training keys remain usable; new visitors persist their key across visits unless
`VITE_DEV_AUTH=1` requests per-tab testing. Existing identities are not merged or
reassigned automatically. Losing browser storage loses access to that identity.

For Linux services, put `TANDEM_TRAINING_ENABLED=1` in the private
`~/.config/filmocracy/backend.env` and restart `filmocracy-api` when ready. The
installer copies this variable from the keys file if it is not already set in
the production environment. Keep one worker and preserve the runtime directory
and checkpoints together. No service installation or remote deployment is needed
for local testing; see [self-hosting](self-hosting.md) for the existing services.
