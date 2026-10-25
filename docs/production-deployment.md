# Filmocracy production deployment: filmocracy.party

Prepared 2026-10-25. Target architecture: Cloudflare Pages at
`https://filmocracy.party`, unified FastAPI on Railway at
`https://api.filmocracy.party`, persistent SQLite at `/data/tandem.db`.
**Nothing has been deployed, DNS has not been changed, and this preparation does not
publish the current branch.** Push, external configuration and deployment remain
separate approval steps. Do not merge into main without approval.

## Repository findings and frontend blocker

Current branch: `codex/railway-deployment-prep`. Available local branches inspected:
`codex/railway-deployment-prep`, `codex/unified-backend-integration`,
`feature/supabase-backend`, and `main`. None contains a frontend package manifest or
complete app: their `frontend/` folders contain notes, an environment template and
session client helper/tests.

A read-only fetch found the teammate's frontend on **`origin/app` at `fcaaa14`**.
It is React + TypeScript + Vite, with `react-router`, a package lock and these scripts:

| Action | Command from the repository root | Result |
| --- | --- | --- |
| Install | `npm --prefix frontend ci` | Install locked dependencies |
| Development | `npm --prefix frontend run dev` | Vite development server |
| Production build | `npm --prefix frontend run build` | `tsc -b && vite build`, output `frontend/dist` |
| Lint | `npm --prefix frontend run lint` | ESLint |

Those commands describe **the `app` branch**, not the current checkout. Its README
specifies Node 20.19+ (team uses Node 24); use Node 24 for Pages when that branch is
ready. The Vite config does not override the default `dist` output directory.

It is a working UI draft, **not a production-integrated application**:

- `src/api/index.ts` hardcodes `/mock-api`; setting `VITE_API_URL` currently has no effect.
- Live snapshots use `EventSource('/mock-api/events')`, not the real session WebSocket.
- `mock-backend/index.ts` runs only inside the Vite dev server and is absent from a
  static Pages deployment/production preview.
- "Google sign-in" currently asks for a name; no GIS ID-token flow is wired.
- Screenshots remain local, and movie recommendations/session state are mocked.
- Mock actions and `Snapshot` differ from FastAPI's session/round APIs; a real adapter
  must map them. Do not replace the backend contract with the mock protocol.

The teammate's app was neither copied, merged, rewritten nor replaced. Per the user's
instruction, **wait for the frontend to be finished**. Its production build/lint and
real-device end-to-end acceptance are pending. Deploying today's draft to Pages
would produce a static bundle whose mock backend is missing.

## 1. Backend on Railway

After push/deployment approval, create an empty service first, configure it, then
connect the approved GitHub branch/commit. Connecting GitHub or changing variables
can trigger a deploy; do not enable autodeploys before approval.

| Railway setting | Exact value |
| --- | --- |
| Repository | `Str0beLite/tandem`, approved release branch/commit |
| Root directory | `/backend` |
| Builder | Existing `backend/Dockerfile` (Dockerfile in the build context) |
| Build command | None; use the Dockerfile |
| Start command | `sh -c 'exec uvicorn unified:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1'` |
| Health check | `/ready`, 120-second timeout |
| Replica/region | One replica in one region |
| Sleep/serverless | Disabled |
| Restart | On failure |

The Dockerfile has the same command. `${PORT:-8000}` expands Railway's assigned
`PORT`; 8000 is only a local fallback. Do not start `tandem.api:app`: it is the
standalone API and does not provide the durable session application. `app:app` is a
compatibility alias for `unified:app`.

Railway's current docs deprecate legacy `railway.json` for new services. Configure
the dashboard values above explicitly; retain `backend/railway.json` as the existing
reference. For a legacy service that still reads it, the config path is
`/backend/railway.json`, independently of the root directory. See the detailed
[Railway handoff](railway-deployment.md).

## 2. Persistent volume and first startup

Attach a Railway volume **to this backend service**, mounted at `/data`, before the
first application startup. Set `TANDEM_DATA_DIR=/data`. Railway supplies
`RAILWAY_VOLUME_MOUNT_PATH`; setting that variable yourself does not create a volume.
Do not use a pre-deploy migration command: volumes are available at runtime.

Startup automatically creates `/data/tandem.db`, applies the existing additive
`CREATE TABLE IF NOT EXISTS` schema and seeds all 5,000 canonical movies plus
200 supplementary metadata records from bundled files. No manual migration, catalog
import, SQLite upload or recommendation retraining is needed on a fresh volume.

On repeated startup, `INSERT OR IGNORE` preserves existing movie metadata and
SQLite user/session/vote records. Movie IDs/vector indices must match the bundled
model catalog or startup fails rather than silently replacing it. Keep database
WAL/SHM files and any checkpoints under `/data` together. A new volume does not
contain developer sessions; transferring an existing DB requires separate approval.

Use one process/replica. Enable Railway volume backups, and test a consistent backup
and restore procedure before relying on production data. Never wipe a volume to fix
a deployment. `/sessions` persists; legacy `/groups` preview membership is in memory.

## 3. Railway variables

Enter these in Railway Variables, not Git or frontend build variables:

```ini
TANDEM_DATA_DIR=/data
GOOGLE_CLIENT_ID=<your existing Google Web OAuth client ID>
YOUTUBE_API_KEY=<server-only key with YouTube Data API v3 enabled>
MUSE_API_KEY=<server-only Meta Model API key>
FRONTEND_ORIGINS=https://filmocracy.party
TANDEM_DEV_AUTH=0
TANDEM_FAKE_ENCODER=0
SWEEP_ENABLED=true
TRAILER_REGION=US
MUSE_BASE_URL=https://api.meta.ai/v1
MUSE_MODEL=muse-spark-1.3
MUSE_REASONING=minimal
MUSE_MAX_TOKENS=4096
```

Angle-bracket values are placeholders, not literal values to enter. Leave `PORT` to
Railway. The image already supplies `HF_HOME` and the catalog/seed checkpoint defaults.
Google's public client ID must match the frontend ID; no Google client secret is
used or required by the current GIS ID-token implementation. No Supabase credentials
are needed. `LLAMA_*` names are obsolete. Unified retraining remains disabled.

CORS and browser WebSocket origin validation both read `FRONTEND_ORIGINS`. Use exact
origins without paths/trailing slashes. Add `https://www.filmocracy.party` or a specific
Pages preview origin only if it will actually serve the app. Do not allow `*` or all
preview hosts. Startup rejects development auth and fake encoding on Railway.

## 4. api.filmocracy.party -> Railway

1. First verify the Railway-generated HTTPS domain and `/ready` work with the attached
   volume. Confirm the service listens on the assigned `PORT`.
2. In backend service Settings -> Networking/Public Networking, add custom domain
   **`api.filmocracy.party`**, targeting that same assigned service port.
3. Railway supplies a CNAME target and a TXT verification record. In Cloudflare DNS
   for `filmocracy.party`, add **both**, copying the exact hostnames and values:

   | Type | Name | Value |
   | --- | --- | --- |
   | CNAME | `api` | Railway's generated target hostname, with no `https://`, path or port |
   | TXT | Exact verification name Railway displays | Exact verification value Railway displays |

4. Start the `api` CNAME as **DNS only** while Railway validates ownership and issues
   its certificate. There is no need to put a Cloudflare Worker or Pages proxy in front
   of FastAPI. Leave existing unrelated DNS/email records intact.
5. Wait for Railway's domain verification and TLS issuance, then open
   `https://api.filmocracy.party/ready`. Missing TXT ownership verification can leave
   a resolving CNAME returning 404. Do not proceed through browser certificate warnings.
6. If you later enable Cloudflare proxying, follow Railway's current Cloudflare/TLS
   guidance and retest sockets; do not change zone-wide SSL settings blindly. The
   DNS-only API record avoids that additional proxy layer for the initial deployment.

Public endpoints have **no `/api` prefix** and **no `:8000` port**:

| Purpose | URL |
| --- | --- |
| API base | `https://api.filmocracy.party` |
| Ready / docs | `https://api.filmocracy.party/ready`, `https://api.filmocracy.party/docs` |
| Session socket | `wss://api.filmocracy.party/sessions/<session-uuid>/ws` |

## 5. Existing frontend on Cloudflare Pages (pending completion)

Do not publish the mock app as the production service. After your teammate finishes
integration and confirms the frontend's source branch:

1. Review/merge the finished frontend into an approved release branch without
   overwriting it. No merge into main is authorized by this guide.
2. Run its locked install, lint and production build above. Confirm `dist/index.html`
   exists, the built app uses the real API, and no `/mock-api` or fake sign-in path
   remains active in the production bundle. Test refresh of `/tv` and `/phone/...`.
3. Cloudflare Dashboard -> Workers & Pages -> create a **Pages** project -> connect
   the existing GitHub repo and the approved frontend branch. Use:

   | Pages setting | Value for the inspected Vite app |
   | --- | --- |
   | Root directory | `frontend` |
   | Build command | `npm run build` |
   | Output directory | `dist` (relative to frontend root) |
   | Node version | `NODE_VERSION=24` |
   | Production API variable | `VITE_API_URL=https://api.filmocracy.party` |
   | Google variable | `VITE_GOOGLE_CLIENT_ID=<same public ID as Railway GOOGLE_CLIENT_ID>` |

4. Vite variables are embedded at build time: changes require a rebuild. They are
   public, so never add `MUSE_API_KEY`, `YOUTUBE_API_KEY`, OAuth secrets or server keys.
   Do not assume a `VITE_*` prefix keeps a value private. Backend `/session-catalog`
   already supplies mapped trailer metadata; any further TMDB client integration
   needs its own review rather than exposing server credentials accidentally.
5. In the finished Vite adapter, read `import.meta.env.VITE_API_URL`, send
   `Authorization: Bearer <fresh GIS credential>` on HTTP calls, and initialize GIS
   with `import.meta.env.VITE_GOOGLE_CLIENT_ID`. Do not send a name as a bearer token.
6. Use `wss://api.filmocracy.party/sessions/{id}/ws`. The existing framework-free
   `connectSession` helper derives `wss:` from an HTTPS API base; it is not yet wired
   into the teammate app. Authenticate with an initial `{"type":"auth","token":"..."}`
   message, renew membership with heartbeats, and reconnect using a fresh token and
   full revisioned snapshot. Do not put tokens in URLs or localStorage.
7. Static Pages cannot run the Vite mock backend. Keep real session transitions on
   FastAPI, and explicitly map its state/round UUIDs into the UI's screen flow.

For a React SPA, verify Pages' SPA fallback works for deep links; do not add a backend
proxy rewrite or a fake API handler to paper over an unfinished adapter. If the final
frontend adds SSR/Pages Functions, revisit these static build settings with its owner.

## 6. filmocracy.party -> Cloudflare Pages

1. Ensure `filmocracy.party` is an active Cloudflare DNS zone in the **same account**
   as the Pages project. If registered elsewhere, add it to Cloudflare and update
   the registrar to Cloudflare's assigned nameservers, preserving existing records.
   Buying the domain alone does not necessarily complete this step.
2. In the Pages project -> Custom domains -> Set up a domain, add **`filmocracy.party`**.
   Let Pages create/verify the apex record and TLS certificate. Associate the domain
   in Pages first; do not merely invent a CNAME at the registrar.
3. If manually prompted, set the apex CNAME target to the project's exact
   `<project>.pages.dev` hostname. Cloudflare handles apex flattening. Do not point
   the apex at Railway or put `api` on Pages.
4. Optionally add `www.filmocracy.party` and redirect it to the apex using Cloudflare
   rules. If www serves the app, include that origin in both CORS and Google's settings.
5. Wait for domain/certificate status to be active, then verify the root and deep
   links over HTTPS on a phone. Preview `pages.dev` origins need explicit Google/CORS
   entries if used for sign-in; prefer the approved production origin for acceptance.

## 7. Google Identity Services

Use the existing Google **Web application** OAuth client, with GIS loaded from
`https://accounts.google.com/gsi/client`. In Google Cloud/Auth Platform -> Clients:

- Authorized JavaScript origins: **`https://filmocracy.party`**. Add www only if used.
  Keep localhost entries only for intentional development testing.
- Ensure consent/testing status permits the team's accounts; add test users if needed.
  Configure branding/authorized domain `filmocracy.party` if the console requires it.
- Set the same client ID in Pages `VITE_GOOGLE_CLIENT_ID` and Railway `GOOGLE_CLIENT_ID`.
- The GIS JavaScript callback returns `credential`, a Google **ID token**. Send that
  token to FastAPI; Google verifies it for the configured client, and the app uses `sub`
  as identity. Do not send an OAuth access token, name, email or user-supplied ID.
- No server-side OAuth exchange or Google client secret is used. No backend redirect
  URI is required for the current callback flow; add one only if the frontend's
  completed implementation explicitly switches to a redirect flow.
- Avoid a blanket restrictive CSP/COOP policy that blocks GIS, its popup or YouTube
  embeds. Review final Pages security headers against Google's integration guide.

## 8. Acceptance checklist after approved deployment

- [ ] `/ready` reports SQLite, 5,000 movies and training disabled; backend logs show
  one worker and the assigned port. Verify actual attached volume and backups.
- [ ] Browser calls from `https://filmocracy.party` pass CORS; other browser origins
  cannot open session sockets. CORS does not replace Google/session authorization.
- [ ] Real GIS sign-in on laptop/TV and **three distinct Google phone accounts** works;
  missing/invalid/expired/wrong-audience tokens fail. Credentials refresh correctly.
- [ ] TV creates a session and displays a QR **join URL on filmocracy.party**, with the
  secure invite token in the fragment. Phone submits it to `/sessions/join`; do not
  use the mock's fixed four-character room code. No token in server access logs.
- [ ] Upload Explore screenshots through `/feeds`; Muse extracts and summarizes tags.
  Provider failures return a recoverable error, and a failed summary uses the average.
- [ ] Prepare the real session queue, confirm no repeats, and verify YouTube trailers
  really play on the TV in the selected region, not just that metadata exists.
- [ ] All devices authenticate their `wss://` sockets, receive matching snapshots and
  heartbeat. Voting uses the current round UUID; three simultaneous votes advance
  exactly once and the TV updates. Replayed votes/skips do not create another round.
- [ ] Unanimous approvals rank above mixed votes. Host skip/end work; unrelated users
  cannot see/control the room. A disconnected phone expires after its lease/sweep.
- [ ] Refresh TV/phone, reconnect with fresh Google tokens and synchronize current
  state without creating a duplicate session. The UI implements reconnect backoff.
- [ ] Restart/redeploy the Railway container with the same volume; votes, members,
  rounds and movie data persist. Verify this **on Railway**, beyond local Docker tests.
- [ ] Logs contain no keys, bearer tokens or screenshot contents. Use isolated test
  sessions; never reset/truncate production data to run acceptance checks.

## Evidence and remaining limits

Local Python and Docker tests cover the backend's state machine, concurrent voting,
reconnect/persistence, provider contracts and production origin/client-ID wiring.
Live provider probes use synthetic content, not personal screenshots. Google verifier
unit tests use a test double; public GIS login and the final frontend aren't verified.
A real Railway volume, public TLS certificates/DNS and WSS must still pass the checks
above. Refer to [the verification log](local-verification.md) for exact test evidence.

Official references: [Railway domains](https://docs.railway.com/networking/domains/working-with-domains),
[Railway volumes](https://docs.railway.com/volumes),
[Railway config compatibility](https://docs.railway.com/config-as-code),
[Pages build settings](https://developers.cloudflare.com/pages/configuration/build-configuration/),
[Pages custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/),
[Google GIS setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid).
