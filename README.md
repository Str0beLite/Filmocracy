# Tandem

**Movie night picks from your group's Instagram feeds.** Everyone uploads a few screenshots of their feed once, joins the host's screen with a QR code, and Tandem serves trailers the whole group will want to watch. You never rate a single movie: your feed already says what your taste is.

Under the hood is a small learned matrix **W** that translates "Instagram taste" into "film taste". It starts as a zero-shot guess and gets better with every 👍 and 👎, live, while the app is running.

## How it works

```
 Explore screenshot ──► tiles ──► Muse Spark ──► tags {"gym": 0.9, "dark humor": 0.6, ...}
                                            │  embed each tag, weighted mean
                                            ▼
                                     x  (384-dim feed vector)
                                            │  ŷ = normalize(W x)
                                            ▼
 movie tag database ──► embed tags ──► t_m per film ──► score = ŷ · t_m ──► 10 recs
                                                                              │
                                     W = I + ABᵀ  ◄── retrain every 20 taps ◄─┘
```

1. **Read the feed.** Each Explore screenshot is split into its tiles using pixel colour alone (`grid.py`), and Meta Muse Spark looks at each tile and writes free-form tags with weights. The tags cover what's on screen ("street food", "deadlift") and how it feels ("cozy", "chaotic energy"). Ads get dropped.
2. **Embed both sides the same way.** Every tag, from the feed or from the movie tag database, goes through one frozen text encoder (`bge-small`). A bag of tags becomes the weighted mean of its tag vectors. No fixed tag lists anywhere: any tag works on either side.
3. **Translate.** W maps the feed vector into film-taste space. On day 0, W is the identity, so tags match by meaning ("dark humor" ≈ "dark comedy").
4. **Recommend.** Films are ranked by cosine to the translated vector. You get the top 8, plus 2 exploration picks so the model can learn beyond what it already believes. Each pick says which of your feed's tags drove it.
5. **Learn live.** Feedback is logged to SQLite. Every 20 taps, W retrains on all feedback so far. The training does two things: it moves W x toward the user's loved-film vector, and it ranks loved films above everything else. The new W only goes live if held-out recall doesn't drop. W is shared, so it learns links like "gym feed → underdog films" from early users and applies them to everyone after.

The full math, and the contract between each piece, are in **[docs/algorithm.md](docs/algorithm.md)**.

## Repo layout

| Path | What's there |
|---|---|
| `backend/` | FastAPI service: vision, embeddings, W, live trainer, SQLite log. [Setup, API and deploy →](backend/README.md) |
| `backend/tandem/` | `grid.py` (Explore tiles), `vision.py` (Muse Spark), `encoder.py` (tag embeddings), `model.py` (W + loss), `trainer.py` (live loop), `recommend.py`, `api.py` |
| `backend/scripts/build_catalog.py` | One-off builder: movie tag database → film vectors |
| `frontend/` | Client app (in progress) |
| `docs/algorithm.md` | How the algorithm works, split into pieces with owners and interfaces |
| `docs/decisions.md` | One-line log of design and stack choices |

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cp .env.example .env              # fill in keys; TANDEM_DEV_AUTH=1 lets you skip Google locally
uvicorn tandem.api:app --reload --env-file .env
```

The movie catalog (5000 MovieLens films) is already committed. Keys, the group API, curl examples and the Railway deploy are in **[backend/README.md](backend/README.md)**.

Tests: `cd backend && TANDEM_FAKE_ENCODER=1 pytest -q`. They use a fake encoder and a synthetic catalog, so they need no keys and no downloads.

## Stack

Python, FastAPI, PyTorch (CPU), `sentence-transformers` (`BAAI/bge-small-en-v1.5`), Meta Muse Spark (Meta Model API, OpenAI-compatible), and SQLite. It deploys as one Docker container on Railway, with a volume at `/data` for the event log and W checkpoints.
