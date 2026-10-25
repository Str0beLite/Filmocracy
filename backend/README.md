# Backend

A FastAPI service that turns a reels feed into 10 film recommendations and keeps learning from the thumbs up and thumbs down people give. One process does all of it: serving, the SQLite event log, and a background thread that retrains the translator W.

## How it works

1. **Taste profiles.** Claude (`claude-haiku-5-5`) rewrites each reel screenshot or caption, and each movie, into the same schema: mood, themes, aesthetic, pacing, setting, who loves this. Ads get flagged and dropped.
2. **Frozen encoder.** `BAAI/bge-small-en-v1.5` turns each profile into a 384-number vector. It is never trained.
3. **Translator W = I + ABᵀ** (rank 8, about 6k parameters). A starts at 0, so on day 0 W is the identity and you get pure zero-shot matching.
4. **Score.** `s(u, m) = τ · logsumexp_i(cos(W rᵢ, m) / τ)`. This is a soft max over reels, so one strong facet of your feed can carry a match on its own.
5. **Serve 10.** The top 8 by score, plus 2 exploration picks drawn at random from ranks 11–50.
6. **Learn live.** Every ~20 feedback events, the trainer warm-starts from the current W and runs 100 Adam steps on the *whole* buffer, using InfoNCE over the full catalog with thumbs-downs as hard negatives. It then checks recall@50 on a held-out set (hidden favourites plus the newest 10% of loves). The new W is hot-swapped in only if it scores at least as well as the current one.

Code map: `tandem/model.py` (W, scoring, loss), `tandem/trainer.py` (loop, gate, hot-swap), `tandem/api.py` (endpoints), `tandem/profiles.py` (Claude), `tandem/store.py` (SQLite).

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

### Build the movie catalog (once, on your laptop)

Download `tmdb_5000_movies.csv` from Kaggle ("TMDB 5000 Movie Dataset"), then run:

```bash
python scripts/build_catalog.py --csv ~/Downloads/tmdb_5000_movies.csv
```

This writes about 4.8k Haiku taste profiles (cached in `catalog/profiles.jsonl`, and a crashed run resumes where it stopped) and embeds them. Commit `catalog/movies.json`, `catalog/movie_vecs.npy` and `catalog/profiles.jsonl`. Use `--no-llm` for a free, rougher catalog built from raw metadata.

### Run

```bash
uvicorn tandem.api:app --reload
pytest -q            # uses a fake encoder + synthetic catalog, no key needed
```

## API

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Current W version, number of events, whether an LLM key is set |
| `POST` | `/feeds` | Multipart: `files` (reel screenshots), `captions` (newline-separated or a JSON list), `user`. Returns `feed_id` and the reel profiles |
| `POST` | `/feeds/{id}/favourites` | `{"titles": [...], "holdout_frac": 0.3}` seeds known loves, with a share hidden for the recall check |
| `GET` | `/feeds/{id}/recs` | 10 films, each with `rec_id`, profile and `because_of_reel` |
| `POST` | `/feedback` | `{"rec_id": 12, "label": "love" \| "seen_loved" \| "nah"}`, or `feed_id` + `movie_id` (TMDB id) instead of `rec_id` |
| `POST` | `/admin/retrain` | Run a training round now (handy on stage) |
| `GET` | `/model` | Every round's recall before and after, plus accepted or rejected, for the live demo chart |
| `GET` | `/movies/search?q=` | Title search, for a favourites picker |

Quick try with captions only:

```bash
curl -F user=ryan -F $'captions=late night tokyo walk, neon rain\nold man fixing watches, slow and quiet' localhost:8000/feeds
curl localhost:8000/feeds/<feed_id>/recs
```

## Deploy (Railway)

1. New project → Deploy from GitHub → this repo. In service settings, set **Root Directory** to `backend`. Railway picks up `Dockerfile` and `railway.json`.
2. Add a **Volume** mounted at `/data`. The SQLite log and W checkpoints live there and survive redeploys.
3. Variables: `ANTHROPIC_API_KEY`.
4. Generate a public domain and point the frontend at it.

Hugging Face Spaces (Docker, free CPU) also works, but its disk is wiped on restart, so the training log would vanish.

## Env vars

| Var | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Needed for screenshots and for good profiles |
| `TANDEM_DATA_DIR` | `backend/data` (`/data` in Docker) | SQLite + checkpoints |
| `TANDEM_RETRAIN_EVERY` | 20 | Feedback events between rounds |
| `TANDEM_MIN_VOTES` | 500 | Don't recommend films with fewer TMDB votes |
| `TANDEM_FAKE_ENCODER` | 0 | 1 = hashing encoder (tests and offline dev) |

All other knobs (rank, τ, λ, learning rate, steps) are in `tandem/config.py`.
