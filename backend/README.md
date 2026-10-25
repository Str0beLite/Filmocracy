# Backend

A FastAPI service that turns screenshots of someone's Instagram feed into 10 film recommendations, and keeps learning from the thumbs up and thumbs down people give. One process does all of it: serving, the SQLite event log, and a background thread that retrains W.

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

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
export LLAMA_API_KEY=...        # Meta Llama API key (llama.developer.meta.com)
```

The vision call goes to any OpenAI-compatible endpoint. Defaults: `LLAMA_BASE_URL=https://api.llama.com/compat/v1/`, `LLAMA_MODEL=Llama-4-Maverick-17B-128E-Instruct-FP8`. To use the same Llama models elsewhere, point those at Together or Groq, or run Ollama locally with `llama3.2-vision`.

### Build the catalog (once, on your laptop)

With the MovieLens tag genome (`ml-32m` or `ml-25m`, unzipped):

```bash
python scripts/build_catalog.py --genome-dir ~/Downloads/ml-32m --top 5000
```

With any other tag database, export one long CSV with columns `movie_id,title,tag,weight` (`year` optional):

```bash
python scripts/build_catalog.py --tags-csv our_movie_tags.csv
```

Commit `catalog/movies.json` and `catalog/movie_vecs.npy`.

### Run

```bash
uvicorn tandem.api:app --reload
pytest -q            # synthetic catalog, no key needed
```

## API

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Current W version, number of films, event count, whether the vision key is set |
| `POST` | `/feeds` | Multipart: `files` (feed screenshots), optional `tags` (JSON `{tag: weight}` with any tags, handy for testing without a key), `user`. Returns `feed_id` and the tags it read |
| `POST` | `/feeds/{id}/favourites` | `{"titles": [...], "holdout_frac": 0.3}` seeds known loves, with a share hidden for the recall check |
| `GET` | `/feeds/{id}/recs` | 10 films, each with `rec_id`, top movie tags, `tmdb_id` (for posters) and `because_of` |
| `POST` | `/feedback` | `{"rec_id": 12, "label": "love" \| "seen_loved" \| "nah"}`, or `feed_id` + `movie_id` instead of `rec_id` |
| `POST` | `/admin/retrain` | Run a training round now (handy on stage) |
| `GET` | `/model` | Every round's recall before and after, plus accepted or rejected, for the live demo chart |
| `GET` | `/movies/search?q=` | Title search, for a favourites picker |

Try it without a key:

```bash
curl -F 'tags={"dark humor":1,"neon night drives":0.7,"gym rat":0.4}' localhost:8000/feeds
curl localhost:8000/feeds/<feed_id>/recs
```

## Deploy (Railway)

1. New project → Deploy from GitHub → this repo. In service settings, set **Root Directory** to `backend`. Railway picks up `Dockerfile` and `railway.json`.
2. Add a **Volume** mounted at `/data`. The SQLite log and W checkpoints live there and survive redeploys.
3. Variables: `LLAMA_API_KEY` (plus `LLAMA_BASE_URL` / `LLAMA_MODEL` if you're not on Meta's API).
4. Generate a public domain and point the frontend at it.

Hugging Face Spaces (Docker, free CPU) also works, but its disk is wiped on restart, so the training log would vanish.

## Env vars

| Var | Default | |
|---|---|---|
| `LLAMA_API_KEY` | none | Needed for screenshots |
| `LLAMA_BASE_URL`, `LLAMA_MODEL` | Meta Llama API, Llama 4 Maverick | Any OpenAI-compatible vision endpoint |
| `TANDEM_DATA_DIR` | `backend/data` (`/data` in Docker) | SQLite + checkpoints |
| `TANDEM_RETRAIN_EVERY` | 20 | Feedback events between rounds |
| `TANDEM_BETA` | 1.0 | Weight of the taste-vector term vs the ranking term |
| `TANDEM_FAKE_ENCODER` | 0 | 1 = hashing encoder instead of bge-small (tests, offline dev) |

All other knobs (rank, τ, λ, learning rate, steps) are in `tandem/config.py`.
