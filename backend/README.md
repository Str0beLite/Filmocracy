> **watchtandem.tech deployment:** See [the production guide](../docs/production-deployment.md) for Railway, Cloudflare Pages, custom domains, Google configuration and the frontend completion blocker.

> **Unified SQLite service:** Docker/Railway run `unified:app`; `app:app` is an alias. Use [the integration guide](../docs/unified-backend.md) for durable QR sessions, atomic votes, authenticated WebSocket updates (with SSE compatibility), metadata migration and deployment. Supabase is no longer required. All recommendation routes below remain available; unified disables model training.
>
> Run from the repository root: `backend/.venv/bin/uvicorn unified:app --app-dir backend --host 0.0.0.0 --port 8000`. Use main's Google ID tokens, GOOGLE_CLIENT_ID, and a YOUTUBE_API_KEY for queue validation. The standalone documentation below retains its original live-training development mode.

# Backend

A FastAPI service that turns screenshots of someone's Instagram feed into film recommendations, for one person or a whole group, and keeps learning from the thumbs up and thumbs down people give. One process does all of it: serving, the SQLite event log, and a background thread that retrains W.

## How it works

Neither side has a fixed tag list. Every tag string is turned into a vector by a frozen text encoder (`BAAI/bge-small-en-v1.5`, a small sentence model on CPU, not an LLM), so a bag of tags of any size becomes one 384-number vector.

1. **Feed vector x.** Each Explore screenshot is split into tiles (`tandem/grid.py`), and Meta Muse Spark reads each tile and writes 5–15 free-form tags with weights from 0 to 1, covering what it shows ("street food", "deadlift") and how it feels ("chaotic energy", "dark humor"). Ads get flagged and dropped. Then x = normalize(Σ wᵢ · E(tagᵢ)) over all the screenshots' tags. This is the only LLM step.
2. **Film vectors tₘ.** The same thing for each film's tags in the database: its strongest 20 genome tags, weighted by relevance, or IDF-weighted tags from a custom CSV. The vectors are then centred on the average film, so tags that every film has don't count.
3. **Translate.** ŷ = normalize(W x) with W = I + ABᵀ (384 × 384, rank-8 update). A starts at 0, so on day 0 W is the identity and tags match by meaning ("dark humor reels" lands near "dark comedy"). The trained part is ~6k parameters however many tags exist.
4. **Score.** score(m) = ŷ · tₘ. Serve the top 8, plus 2 exploration picks drawn at random from ranks 11–50. Each rec says which of your feed's tags pushed it up (`because_of`).
5. **Learn live.** Every ~20 feedback events, the trainer warm-starts from the current W and runs 100 Adam steps over the *whole* buffer, minimising three terms:
   - **taste:** 1 − cos(W x, yᵤ), where yᵤ is the mean vector of the films that user loves (nudged away from ones they passed on). This is "reach their film taste from their Instagram taste alone".
   - **ranking:** InfoNCE over the full catalog, so loved films beat every other film. Thumbs-downs are hard negatives.
   - **λ‖ABᵀ‖²:** stays at zero-shot wherever there's no data.

   The trainer then checks recall@50 on a held-out set (hidden favourites plus the newest 10% of loves). The new W is hot-swapped in only if it scores at least as well. W is shared, so it learns cross-vocabulary links like "gym" → "underdog story" from early users and applies them to everyone after.

Code map: `tandem/model.py` (W, loss), `tandem/trainer.py` (loop, gate, hot-swap), `tandem/grid.py` (Explore tiles), `tandem/vision.py` (Muse Spark), `tandem/encoder.py` (tag embeddings), `tandem/api.py` (endpoints), `tandem/store.py` (SQLite).

## Setup

### 1. Get the keys

Create an ignored `backend/.env` using the variables below and the [Railway production variable table](../docs/railway-deployment.md#production-variables). Use `MUSE_*` names; environment example files are excluded from this integration commit and the tracked example may still show legacy `LLAMA_*` names.

| Key | Needed for | Where to get it |
|---|---|---|
| `MUSE_API_KEY` | Reading feed screenshots | [dev.meta.ai](https://dev.meta.ai) → sign in → **API keys** → create (US public preview, pay as you go). Without it, `POST /feeds` still accepts `tags` JSON (handy for testing). |
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

The vision call goes to the Meta Model API's OpenAI-compatible Chat Completions. Defaults: `MUSE_BASE_URL=https://api.meta.ai/v1`, `MUSE_MODEL=muse-spark-1.3`. Overrides must support the same image, structured-output and reasoning request fields.

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

### 5. Test and train from the terminal

With the server running in dev-auth mode, each teammate runs this with their own name:

```bash
python scripts/play.py alice                       # type your feed as tags, add films you love, then rate recs
python scripts/play.py alice --shots ~/Pictures/feed/*.png   # read real screenshots instead (needs MUSE_API_KEY)
python scripts/play.py alice --boost heist         # what a host's mood pick does to the list
```

Keys: `y` want to watch, `s` seen it and loved it, `f` loved it and save it as a favourite, `n` nah, Enter for don't know it, and `+title` to search any film and save it as a favourite. Each rating is one training event, and favourites also feed the held-out check (about 30% are hidden). W retrains on its own every 20 events (`TANDEM_RETRAIN_EVERY`), and the server log prints `[trainer] vN ACCEPTED|rejected recall@50 old -> new`. You can force a round with `curl -XPOST -H "X-Admin-Token: $TANDEM_ADMIN_TOKEN" localhost:8000/admin/retrain`. `GET /model` lists every round.

- A new W only goes live when held-out recall doesn't drop. With only a few events, the held-out set is one or two films, so expect a lot of rejections at first.
- Recall is checked against films you listed as already loved (30% of them are hidden) plus the newest 10% of likes. List 5 to 10 favourites per person so the check means something.
- Everything lives in `data/` (`tandem.db` and `checkpoints/`). Delete that folder to start over from the seed W.

### 6. The pre-trained W and fake users

`catalog/w_seed.pt` is a W that's already trained. A fresh database (a new `data/`, or a new Railway volume) starts from it instead of from W = I, and the version still shows as `v0`. Delete the file, or point `TANDEM_SEED_W` somewhere else, to start from W = I.

It was trained on 60 fake users from `scripts/seed_fake.py`, plus about 140 real ratings from the team. On held-out favourites, recall@50 went from 0.33 with W = I to 0.51.

```bash
python scripts/seed_fake.py --api http://localhost:8000      # 60 fake users, about 1900 ratings, a few minutes
```

- **How the fake users work.** Each fake user is built from 1 or 2 of 14 personas (gym, skincare, true crime, anime, cinephile, space, horror, parents, history, streetwear, memes, sad indie, gamer, outdoors). A persona pairs Instagram-style tags ("deadlift") with the catalog tags of the films it likes ("sports", "martial arts"). On top of that, everyone leans toward the hits: the most-rated films get loved whatever the feed says.
- **What it teaches W.** W learns the rules written into the personas, not real taste. That's fine for a demo, but remove the fake data once real users show up. Every fake user id starts with `fake-`: delete those feeds and their events and recs from the database, then retrain.

## Handoff: what's still open

The algorithm is done: tags to x, W, recs, group lists, live training and the recall gate. Two pieces are owned by teammates now.

**1. Screenshots → feed tags (`tandem/vision.py`).** Upstream reports real Explore screenshot testing; this branch verified a synthetic-image request (see the verification log). The contract the rest of the code depends on:
- `read_screenshots([(bytes, media_type), ...])` returns one `(is_noise, {tag: weight 0..1})` per screenshot.
- `summarize(readings)` (async) returns `({tag: weight}, n_dropped)`: one text-only call sums up every tile's tags, falling back to `merge()`'s plain average.
- `POST /feeds` passes that dict to `catalog.feed_vector`, which turns it into x.

Anything that produces lowercase free-form tags with weights works: a different model, a different prompt, or OCR of captions. Changing the encoder (`bge-small`) or `DIM` means rebuilding the catalog and throwing away `w_seed.pt` and every checkpoint.

**2. The server and accounts (Supabase rewrite).** The algorithm only needs a stable user id per person. Today that's the Google `sub`, or the dev-auth name. What the backend still lacks:
- **Groups are in memory** (`state["groups"]` in `api.py`), so they're lost on every restart.
- **Sessions don't exist yet.** There's no current trailer, no vote tally, no end rule. A session layer would pick a film from `POST /groups/{id}/recs`, show it, and send each vote to `POST /feedback` with `{movie_id, label}`: yes is `love`, no is `nah`.
- **Feeds, events and W versions are in SQLite** on the Railway volume. Moving them to Supabase means rewriting `store.py` behind the same methods.

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
3. **Variables:** `MUSE_API_KEY`, `GOOGLE_CLIENT_ID`, `TANDEM_ADMIN_TOKEN` (plus `MUSE_BASE_URL` / `MUSE_MODEL` to change the model). Don't set `TANDEM_DEV_AUTH`.
4. **Settings → Networking → Generate Domain.** Check `https://<domain>/health` shows `"movies": 5000`.
5. Frontend (Vercel): set `VITE_API_URL=https://<railway domain>`, plus `VITE_GOOGLE_CLIENT_ID` and `VITE_TMDB_TOKEN`. Add the Vercel domain to the OAuth client's **Authorized JavaScript origins**.

The image bakes in torch (CPU) and the bge-small weights, so the first build takes a few minutes and boots without downloads. CORS allows any origin, which is fine because auth is a Bearer header, not cookies.

Hugging Face Spaces (Docker, free CPU) also works, but its disk is wiped on restart, so the training log would vanish.

## Env vars

| Var | Default | |
|---|---|---|
| `MUSE_API_KEY` | none | Needed for screenshots |
| `MUSE_BASE_URL`, `MUSE_MODEL` | Meta Model API, `muse-spark-1.3` | Any OpenAI-compatible vision endpoint |
| `GOOGLE_CLIENT_ID` | none | OAuth web client id. Unset = every signed-in endpoint returns 401 |
| `TANDEM_ADMIN_TOKEN` | none | Unset = `/admin/retrain` returns 403 |
| `TANDEM_SEED_W` | `catalog/w_seed.pt` | Pre-trained W a fresh database starts from; point at a missing file to start at W = I |
| `TANDEM_DEV_AUTH` | 0 | 1 = `Bearer <name>` signs in as `<name>`. Local only |
| `TANDEM_TAG_BOOST` | 0.15 | Score added for a boost-tag match. Real scores span ~0 (median) to ~0.3 (top), so 0.15 nearly fills the top 10 with tagged films (ranked by taste among them). Try 0.05 for a nudge |
| `TANDEM_DATA_DIR` | `backend/data` (`/data` in Docker) | SQLite + checkpoints |
| `TANDEM_RETRAIN_EVERY` | 20 | Feedback events between rounds |
| `TANDEM_BETA` | 1.0 | Weight of the taste-vector term vs the ranking term |
| `TANDEM_FAKE_ENCODER` | 0 | 1 = hashing encoder instead of bge-small (tests, offline dev) |

All other knobs (rank, τ, λ, learning rate, steps) are in `tandem/config.py`.

See the [Railway production handoff](../docs/railway-deployment.md) for current dashboard settings, production variables, approval boundaries and the post-deployment checklist.

For the development-only vision demo with the unified API, serve `backend/scripts` with `python3 -m http.server 5173 --directory backend/scripts` and open `http://localhost:5173/vision_demo.html`. Keep the API on port 8000 with `TANDEM_DEV_AUTH=1` locally. This matches the default allowed frontend origin; opening the file directly has Origin `null` and is intentionally not allowed by unified CORS. Do not enable development auth on Railway.
