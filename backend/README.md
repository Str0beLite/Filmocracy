# Backend

Two FastAPI apps live here:

- **[Session service](#session-service)** (`app.py`): Supabase auth, sessions, QR invitations, voting rounds, heartbeats and Realtime.
- **[Recommendation service](#recommendation-service)** (`tandem/`): feed screenshots → taste embeddings, the learned W, per-member + group rec lists, live training.

They aren't wired together yet. The hook is `recommendations.py`: swap `MockRecommendationProvider` for one that calls the recommendation service.

# Session service

FastAPI + Supabase Postgres/Auth/Realtime. Schema and relationships are documented
in [the backend plan](../docs/backend-plan.md); versioned SQL is in
[`supabase/migrations`](../supabase/migrations). Embeddings are deferred.

## Setup and run

Python 3.9+; from the repository root:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install pip==25.3
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install --no-deps -e backend
```

Create an ignored local backend/.env with SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY,
and SUPABASE_SECRET_KEY. Enable **Anonymous Sign-Ins** in Supabase Auth for guest phones and TV. Set
FRONTEND_ORIGINS to the frontend origins, comma-separated. With those variables
exported into the shell, one command runs the service and disconnect sweeper:

```bash
backend/.venv/bin/uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000
```

The server does not load .env automatically: use your environment manager or
`set -a; source backend/.env; set +a` before running it. API docs: /docs.
Health: /health. Never place SUPABASE_SECRET_KEY in frontend variables.

Frontend developers: start with [the integration guide](../docs/frontend-integration.md)
and [generated OpenAPI](../docs/openapi.json). Deployment is reviewed in
[deployment readiness](../docs/deployment-readiness.md); nothing is deployed.

## API contract

All endpoints except /health require Authorization: Bearer <Supabase user JWT>.
Supabase Auth verifies the token; user database calls forward that JWT, so RLS
and auth.uid() remain effective. Direct browser RPC calls enforce the same rules.

| Endpoint | Body / behavior |
| --- | --- |
| POST /sessions | `{ "display_name": "TV" }`; returns session_id + invite_token |
| POST /sessions/join | `{ "display_name": "Alice", "invite_token": "…" }` |
| GET /sessions/{id} | Member-only session state, rounds, electorate, votes, queue |
| POST /sessions/{id}/invitation | Host rotates invitation and receives new token |
| POST /sessions/{id}/queue | Host appends mock provider's catalog IDs, idempotently |
| POST /sessions/{id}/control | `{ "action": "start" }`, `skip` with expected_round_id, or `end` |
| POST /sessions/{id}/votes | `{ "round_id": "UUID", "value": 1 }`; -1 for dislike |
| POST /sessions/{id}/heartbeat | Phone renews lease every 10 seconds |
| POST /sessions/{id}/leave | Stops participating immediately |

The QR encodes a frontend join URL (prefer `/join#token=…` to avoid server access
logs containing invitation tokens). The frontend extracts the fragment and sends
the token in the join request body. The database stores only its SHA-256 hash.

Create -> phones join -> queue -> host starts -> phones heartbeat/vote. Current
round is the voting_rounds row with closed_at NULL. The TV is a nonvoting host.
New members wait until the next round. Expired voters cannot reenter the same
electorate. A round needs at least one vote before it completes automatically;
an empty/disconnected room waits for host skip/end. When the queue is exhausted,
the session returns to lobby; prepare another queue then start again.

Only the sweep uses the server secret. Keep the service running: it checks leases
and session expiry every 10 seconds. Votes and heartbeats also check expiry. A
disconnected voter stops blocking after 45 seconds plus up to 10 seconds for sweep.
Multiple backend workers are safe because the database serializes each session.
Use one worker for the demo to avoid duplicate sweeps. SWEEP_ENABLED=false is used
only by fixture-isolated tests, or when another process explicitly owns sweeping.

The public tables deny direct mutations except a user's own profile name.
Session writes use identity-checked RPCs; no request accepts a user_id to vote for.
Session members can see each other's votes. RLS isolates unrelated sessions.

## Recommendation integration

`recommendations.py` defines RecommendationProvider and RecommendationContext.
Replace the provider instance in app.py when the teammate's implementation is
ready. MockRecommendationProvider preserves catalog order, removes queued/shown
IDs and duplicates, and limits the list. It computes no recommendations.
The mock reads the first 100 catalog IDs; it is a demo fixture, not a catalog
paginator. Import actual movie metadata with server-side tooling before the demo.
No movies or embedding vectors are seeded by migrations.

Provider work runs outside database locks. Queue installation is atomic and
host-only; votes atomically close the current round and open a queued movie.
No external API or algorithm call happens inside a voting transaction.

## Verification

```bash
backend/.venv/bin/python -m unittest discover -s backend/tests -v
node --test frontend/session-client.test.mjs
backend/.venv/bin/ruff check backend
backend/.venv/bin/python -m build backend
```

Run tests/database.sql through Supabase SQL tooling as postgres (or psql with
ON_ERROR_STOP=1). It impersonates authenticated users and service_role, asserts
authorization/lifecycle/constraints/publication behavior, and rolls back fixtures.
Do not execute it using a public client or the service-role REST API.

Migrations were applied to tandem and these database tests were run there. A
separate two-transaction concurrent-vote check stored both final votes and
opened exactly one successor; its temporary committed fixtures were deleted.
SQL rollback tests can consume identity sequence values; gaps are harmless.

For another project, link using Supabase CLI then use `supabase db push`. Do not
reapply SQL manually to tandem: its migration history already records these files.

## Live API and Realtime tests

The existing tandem project is approved for hackathon development/testing. Both
migrations and all eight application tables were inspected before live writes.
backend/.env.test is gitignored and must remain local, owner-readable only. Set
TEST_SUPABASE_URL, TEST_SUPABASE_PUBLISHABLE_KEY, TEST_SUPABASE_SECRET_KEY,
TEST_PROJECT_REF, TEST_ALLOW_WRITES=1, and TEST_ALLOW_EXISTING_PROJECT=1 for the
approved tandem development project. Never print or commit this file.

```bash
set -a
source backend/.env.test
set +a
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_live*.py' -v
```

Without test settings, live tests report SKIPPED, not a live pass. The API test
uses real Auth -> FastAPI ASGI HTTP -> Supabase, simulating TV, three phones, and
an outsider. It waits for a real 45-second lease to expire, so allow about 1–2
minutes. Recommendation code is neither changed nor invoked; the host enqueues
the run's own fixture movie IDs through the database integration boundary.

The Realtime test opens actual WebSockets using Supabase's documented JSON 1.0
protocol and the dev-only websockets dependency. It checks all six published
tables, an outsider receiving no row events, refreshed-identity reconnection,
and a snapshot containing votes missed while disconnected. Postgres Changes row
authorization is separate from rejecting a channel join; see the frontend guide.

Each live test generates uniquely named confirmed Auth users and a unique movie
provider namespace. Cleanup deletes sessions hosted by those generated identities,
then those users, and movies with that exact provider namespace. Cleanup failures
fail the suite and identify the run ID for targeted investigation. The tests never
reset, truncate, drop, or migrate the database. The background global sweep is
disabled during tests to avoid touching unrelated development sessions. SIGKILL
can bypass cleanup; do not compensate with unscoped deletes.

tests/three_phones.sql is a separate rollback-only database verification with all
queries scoped to its own fixtures; it does not call the global sweep. It has run
successfully against tandem. The older database.sql remains historical verification;
prefer the scoped test when unrelated development sessions may exist.

## Catalog preparation

[TMDB import plan and commands](../docs/movie-catalog.md). The importer is dry-run
by default, inserts only missing movie IDs, and has no writes to other tables.
The approved import added 200 TMDB movies with trailer URLs to tandem. Repeating
the same source set added zero duplicates. Importer unit tests use synthetic TMDB
responses; trailer playback still needs verification in the intended browser.

# Recommendation service

A FastAPI service that turns screenshots of someone's Instagram feed into film recommendations, for one person or a whole group, and keeps learning from the thumbs up and thumbs down people give. One process does all of it: serving, the SQLite event log, and a background thread that retrains W.

## How it works

Neither side has a fixed tag list. Every tag string is turned into a vector by a frozen text encoder (`BAAI/bge-small-en-v1.5`, a small sentence model on CPU, not an LLM), so a bag of tags of any size becomes one 384-number vector.

1. **Feed vector x.** A Meta Llama vision model reads each feed screenshot and writes 5–15 free-form tags with weights from 0 to 1, covering what it shows ("street food", "deadlift") and how it feels ("chaotic energy", "dark humor"). Ads get flagged and dropped. Then x = normalize(Σ wᵢ · E(tagᵢ)) over all the screenshots' tags. This is the only LLM step.
2. **Film vectors tₘ.** The same thing for each film's tags in the database: its strongest 20 genome tags, weighted by relevance, or IDF-weighted tags from a custom CSV. The vectors are then centred on the average film, so tags that every film has don't count.
3. **Translate.** ŷ = normalize(W x) with W = I + ABᵀ (384 × 384, rank-8 update). A starts at 0, so on day 0 W is the identity and tags match by meaning ("dark humor reels" lands near "dark comedy"). The trained part is ~6k parameters however many tags exist.
4. **Score.** score(m) = ŷ · tₘ. Serve the top 8, plus 2 exploration picks drawn at random from ranks 11–50. Each rec says which of your feed's tags pushed it up (`because_of`).
5. **Learn live.** Every ~20 feedback events, the trainer warm-starts from the current W and runs 100 Adam steps over the *whole* buffer, minimising three terms:
   - **taste:** 1 − cos(W x, yᵤ), where yᵤ is the mean vector of the films that user loves (nudged away from ones they passed on). This is "reach their film taste from their Instagram taste alone".
   - **ranking:** InfoNCE over the full catalog, so loved films beat every other film. Thumbs-downs are hard negatives.
   - **λ‖ABᵀ‖²:** stays at zero-shot wherever there's no data.

   The trainer then checks recall@50 on a held-out set (hidden favourites plus the newest 10% of loves). The new W is hot-swapped in only if it scores at least as well. W is shared, so it learns cross-vocabulary links like "gym" → "underdog story" from early users and applies them to everyone after.

Code map: `tandem/model.py` (W, loss), `tandem/trainer.py` (loop, gate, hot-swap), `tandem/vision.py` (Llama), `tandem/encoder.py` (tag embeddings), `tandem/api.py` (endpoints), `tandem/store.py` (SQLite).

## Setup

### 1. Get the keys

Copy `backend/.env.example` to `backend/.env` and fill it in. `.env` is gitignored.

| Key | Needed for | Where to get it |
|---|---|---|
| `LLAMA_API_KEY` | Reading feed screenshots | [llama.developer.meta.com](https://llama.developer.meta.com) → sign in → **API keys** → create. Without it, `POST /feeds` still accepts `tags` JSON (handy for testing). |
| `GOOGLE_CLIENT_ID` | Sign-in (every endpoint except `/health`, `/model`, `/movies/search`) | [Google Cloud console](https://console.cloud.google.com/apis/credentials) → create a project → **OAuth consent screen** (External, add yourself as a test user) → **Credentials → Create credentials → OAuth client ID → Web application**. Under **Authorized JavaScript origins** add `http://localhost:5173` and, later, your Vercel domain. Use the same client id in the frontend's `VITE_GOOGLE_CLIENT_ID`. No client secret is needed. |
| `TANDEM_ADMIN_TOKEN` | `POST /admin/retrain` | Any long random string: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. If it's unset, the endpoint is locked. |

TMDB (posters, trailers, overviews) isn't a backend key. Recs carry `tmdb_id`, and the frontend fetches the details from TMDB itself (`VITE_TMDB_TOKEN`, from [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api), the "API Read Access Token").

### 2. Install

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

The vision call goes to any OpenAI-compatible endpoint. Defaults: `LLAMA_BASE_URL=https://api.llama.com/compat/v1/`, `LLAMA_MODEL=Llama-4-Maverick-17B-128E-Instruct-FP8`. To use the same Llama models elsewhere, point those at Together or Groq, or run Ollama locally with `llama3.2-vision`.

### 3. Catalog (already built and committed)

`catalog/` holds the 5000 most-rated MovieLens 25M films that have tag-genome scores: id, title, year, `tmdb_id` and their 20 strongest tags, plus one tag vector per film. Rebuild it only if you change the film set:

```bash
curl -LO https://files.grouplens.org/datasets/movielens/ml-25m.zip && unzip ml-25m.zip -d ~/Downloads
python scripts/build_catalog.py --genome-dir ~/Downloads/ml-25m --top 5000    # ~1 min
```

With any other tag database, export one long CSV with columns `movie_id,title,tag,weight` (`year` optional) and pass `--tags-csv our_movie_tags.csv`. Commit `catalog/movies.json` and `catalog/movie_vecs.npy` afterwards.

### 4. Run

```bash
uvicorn tandem.api:app --reload --env-file .env
TANDEM_FAKE_ENCODER=1 pytest -q      # synthetic catalog, no keys needed
```

To try it before Google is set up, put `TANDEM_DEV_AUTH=1` in `.env`. Then `Authorization: Bearer <name>` signs you in as `<name>`, with no check at all, so never set it on Railway.

```bash
curl -H 'Authorization: Bearer alice' -F 'tags={"dark humor":1,"neon night drives":0.7}' localhost:8000/feeds
curl -H 'Authorization: Bearer bob'   -F 'tags={"gym":1,"protein shakes":0.6}' localhost:8000/feeds
curl -H 'Authorization: Bearer host' -H 'Content-Type: application/json' -d '{"user_ids":["alice","bob"]}' localhost:8000/groups
curl -H 'Authorization: Bearer host' -H 'Content-Type: application/json' -d '{"boost":["heist"],"exclude":[]}' localhost:8000/groups/<group_id>/recs
curl -H 'Authorization: Bearer alice' -H 'Content-Type: application/json' -d '{"movie_id":6,"label":"love"}' localhost:8000/feedback
```

## API

Everything except `/health`, `/model` and `/movies/search` needs `Authorization: Bearer <Google ID token>` (the `credential` that Google Identity Services hands the frontend). The user is the token's Google account id (`sub`).

A user's taste embedding is the `x` of the feed they uploaded most recently. It never leaves the server: you call by user id or group id, and the backend scores with whatever W is live right now.

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Current W version, number of films, event count, whether the vision key is set |
| `GET` | `/me` | `{user, feed_id, tags}` for your latest feed, or `feed_id: null`, meaning send them to onboarding |
| `POST` | `/feeds` | Onboarding. Multipart: `files` (feed screenshots) and/or `tags` (JSON `{tag: weight}`). Becomes your current embedding. Returns `feed_id` and the tags it read |
| `POST` | `/groups` | Host creates a session: `{"user_ids": [...]}` (may be empty). The caller is the host, not a member. Returns `{group_id, host, members}`. **409** `{"detail": {"needs_onboarding": [ids]}}` if someone has no feed yet |
| `POST` | `/groups/{gid}/join` | The signed-in phone joins (QR code flow); the group's average embedding is recomputed. 409 if you have no feed yet |
| `GET` | `/groups/{gid}` | Host and member ids |
| `POST` | `/groups/{gid}/recs` | `{"boost": [tags], "exclude": [movie ids]}`. Returns `{group_id, w_version, users: {user_id: [rec × 10]}, group: [rec × 10]}`: one list per member from their own embedding, plus one from the group's average embedding. Host or members only. Picking which trailer to show from these lists is the caller's job |
| `GET` | `/feeds/{id}/recs?boost=a&boost=b` | 10 recs for one of your own feeds |
| `POST` | `/feedback` | A vote. `{"movie_id": 6, "label": "love" \| "seen_loved" \| "nah"}` goes on your latest feed (group yes → `love`, no → `nah`). `{"rec_id": 12, "label": ...}` also works for per-user recs |
| `POST` | `/feeds/{id}/favourites` | `{"titles": [...], "holdout_frac": 0.3}` seeds known loves, with a share hidden for the recall check |
| `POST` | `/admin/retrain` | Header `X-Admin-Token`. Runs a training round now (handy on stage) |
| `GET` | `/model` | Every round's recall before and after, plus accepted or rejected, for the live demo chart |
| `GET` | `/movies/search?q=` | Title search, for a favourites picker |

A **rec** looks like `{rec_id, id, title, year, tmdb_id, tags, score, because_of}`. In the `group` list, `rec_id` is null and `because_of` is empty, so vote on those with `movie_id`.

**Tag boost:** films whose catalog tags include any `boost` tag get `+0.15` (`TANDEM_TAG_BOOST`) before ranking. Matching is exact after lowercasing and collapsing whitespace, so send catalog tags (`/movies/search` shows some; the catalog uses 1,116, such as `heist`, `feel-good`, `dark comedy`).

**Groups live in memory.** A redeploy or restart drops open sessions. Feeds, votes and W are in SQLite and survive.

## Deploy (Railway)

1. New project → **Deploy from GitHub repo** → this repo. In the service's **Settings**, set **Root Directory** to `backend`. Railway picks up `Dockerfile` and `railway.json`, and the health check is `/health`.
2. **Add a Volume** to the service, mounted at `/data`. The SQLite log and W checkpoints live there and survive redeploys.
3. **Variables:** `LLAMA_API_KEY`, `GOOGLE_CLIENT_ID`, `TANDEM_ADMIN_TOKEN` (plus `LLAMA_BASE_URL` / `LLAMA_MODEL` if you're not on Meta's API). Don't set `TANDEM_DEV_AUTH`.
4. **Settings → Networking → Generate Domain.** Check `https://<domain>/health` shows `"movies": 5000`.
5. Frontend (Vercel): set `VITE_API_URL=https://<railway domain>`, plus `VITE_GOOGLE_CLIENT_ID` and `VITE_TMDB_TOKEN`. Add the Vercel domain to the OAuth client's **Authorized JavaScript origins**.

The image bakes in torch (CPU) and the bge-small weights, so the first build takes a few minutes and boots without downloads. CORS allows any origin, which is fine because auth is a Bearer header, not cookies.

Hugging Face Spaces (Docker, free CPU) also works, but its disk is wiped on restart, so the training log would vanish.

## Env vars

| Var | Default | |
|---|---|---|
| `LLAMA_API_KEY` | none | Needed for screenshots |
| `LLAMA_BASE_URL`, `LLAMA_MODEL` | Meta Llama API, Llama 4 Maverick | Any OpenAI-compatible vision endpoint |
| `GOOGLE_CLIENT_ID` | none | OAuth web client id. Unset = every signed-in endpoint returns 401 |
| `TANDEM_ADMIN_TOKEN` | none | Unset = `/admin/retrain` returns 403 |
| `TANDEM_DEV_AUTH` | 0 | 1 = `Bearer <name>` signs in as `<name>`. Local only |
| `TANDEM_TAG_BOOST` | 0.15 | Score added for a boost-tag match. Real scores span ~0 (median) to ~0.3 (top), so 0.15 nearly fills the top 10 with tagged films (ranked by taste among them). Try 0.05 for a nudge |
| `TANDEM_DATA_DIR` | `backend/data` (`/data` in Docker) | SQLite + checkpoints |
| `TANDEM_RETRAIN_EVERY` | 20 | Feedback events between rounds |
| `TANDEM_BETA` | 1.0 | Weight of the taste-vector term vs the ranking term |
| `TANDEM_FAKE_ENCODER` | 0 | 1 = hashing encoder instead of bge-small (tests, offline dev) |

All other knobs (rank, τ, λ, learning rate, steps) are in `tandem/config.py`.
