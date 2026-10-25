# Backend

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
