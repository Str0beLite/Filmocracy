# How the Tandem recommender works

A handoff guide to the backend in `backend/`. It splits the system into three pieces with clear contracts, so each piece can be worked on alone:

| Piece | Owner | Files |
|---|---|---|
| **A. Screenshot → feed embedding** | teammate | `tandem/vision.py`, `tandem/encoder.py`, `Catalog.feed_vector` |
| **B. Movie taste embedding → recommendations** | teammate | `scripts/build_catalog.py`, `tandem/catalog.py`, `tandem/recommend.py` |
| **C. The translator W and live training** | Ryan | `tandem/model.py`, `tandem/trainer.py` |

`tandem/api.py` wires the pieces together. `tandem/store.py` is the SQLite log.

## The big picture

```
 feed screenshots                                   movie tag database
        │                                                   │
        ▼  (A) Llama vision                                  ▼  (B) build_catalog.py
 {tag: weight}  "gym": 0.9, "dark humor": 0.6       {tag: relevance} per film
        │                                                   │
        ▼  (A) embed each tag, weighted mean                 ▼  (B) embed each tag, weighted mean, centre
 x  ∈ R^384, unit length                            t_m ∈ R^384, unit length  (one per film)
        │                                                   │
        ▼  (C) translate                                     │
 ŷ = normalize(W x)   ─────────── cosine ──────────────────┘
        │
        ▼  (B) rank, 8 best + 2 exploration, explain
 10 recs  ──►  user taps love / seen_loved / nah  ──►  (C) retrain W every 20 taps
```

The key idea is that **both sides are bags of tags of any size.** Every tag string is turned into a vector by one frozen text encoder (`BAAI/bge-small-en-v1.5`, 384 dims, never trained). A bag becomes one vector by taking the weighted mean. So Instagram language and movie-database language end up in the same space, and **W** learns how one maps onto the other. For example, it can learn that people whose feeds say "gym" love films tagged "underdog story", even though the words never overlap.

## The math

**Tag encoder.** For any tag string $s$, $E(s) \in \mathbb{R}^{384}$ with $\lVert E(s) \rVert = 1$.

**Feed vector (piece A).** Take the tags $\{(s_i, w_i)\}$ read from all non-ad screenshots, with weights averaged across screenshots:

$$x = \operatorname{normalize}\Big(\sum_i w_i\, E(s_i)\Big)$$

**Film vector (piece B).** Take the film's tags $\{(s_j, r_j)\}$: the top 20 genome tags weighted by relevance, or IDF-weighted tags from a custom CSV. Then

$$\tilde t_m = \operatorname{normalize}\Big(\sum_j r_j\, E(s_j)\Big), \qquad \mu = \operatorname{mean}_m \tilde t_m, \qquad t_m = \operatorname{normalize}(\tilde t_m - \mu)$$

Centring on $\mu$, the "average film", removes what every film shares, so cosine rewards what makes a film distinctive. Feed vectors are **not** centred, because centring an unrelated feed would push it toward oddball films.

**Translate and score (pieces C + B).**

$$\hat y = \operatorname{normalize}(W x), \qquad W = I + AB^\top,\ A, B \in \mathbb{R}^{384 \times 8}, \qquad \text{score}(m) = \hat y \cdot t_m$$

$A$ starts at 0, so on day 0 $W = I$ and tags match purely by meaning. Training only ever moves the low-rank part (~6k numbers).

**Training loss (piece C).** For each user $u$ with loved films $P_u$ and passed films $N_u$:

$$y_u = \operatorname{normalize}\Big(\overline{t}_{P_u} - 0.5\, \overline{t}_{N_u}\Big)$$

$$\mathcal{L} = \beta\,\big(1 - \hat y_u \cdot y_u\big) \;+\; \text{InfoNCE}\big(\text{loved film vs. whole catalog},\ \tau = 0.05,\ N_u \text{ up-weighted} \times 5\big) \;+\; 0.5\,\text{unlikelihood}(N_u) \;+\; \lambda \lVert AB^\top \rVert^2$$

In words, the three terms do this:
1. **Taste:** from the Instagram vector alone, land on the user's film-taste vector.
2. **Ranking:** score each loved film above every other film, with thumbs-downs pushed down hard.
3. **Regulariser:** stay near zero-shot wherever there is no data.

**Live loop (piece C).** The loop retrains every 20 feedback events. Each round warm-starts from the current $A, B$ and runs 100 Adam steps on the whole buffer. The new W is gated on held-out recall@50, where the held-out set is hidden favourites plus the newest 10% of loves. It is swapped in only if recall doesn't drop. Every round is logged to the `models` table and shown at `GET /model`.

## Contracts between the pieces

These are the things that must stay true. Everything else inside a piece can change freely.

| Contract | Detail |
|---|---|
| Embedding space | Both sides use **the same encoder** (`config.EMBED_MODEL`) and `config.DIM = 384`. Changing the encoder means rebuilding the catalog **and** throwing away trained W checkpoints. |
| Feed vector `x` | `np.float32`, shape `(384,)`, unit length. Produced only by `Catalog.feed_vector(tags)`. Stored in `feeds.x`. |
| Feed tags | `dict[str, float]`, lowercase, whitespace-collapsed, ≤ 60 chars, weights in `[0, 1]`. Stored in `feeds.tags` and used for the `because_of` explanation. |
| Film vectors | `Catalog.vecs`, `np.float32`, shape `(n_movies, 384)`, rows unit length, already centred. Row `i` ↔ `Catalog.movies[i]`. |
| Catalog files | `catalog/movies.json` (list of `{id, title, year, tmdb_id?, popularity?, tags: {tag: weight}}`) and `catalog/movie_vecs.npy` (float16, uncentred, same order). Rebuilding changes movie indices, so wipe `data/` (old events point at old indices). |
| Model | `model(x_tensor) -> ŷ`, and `model.W()` gives the full 384×384 matrix. The trainer exposes `trainer.current() -> (version, model)`. Readers just call `current()`; the swap is a single reference assignment. |

## Piece A: screenshot → feed embedding

Flow: `POST /feeds` (multipart `files`) → `vision.read_screenshots(shots)` → `[(is_noise, {tag: w})]` per screenshot → `vision.merge()` averages the non-noise ones → `Catalog.feed_vector(tags)` → `x`.

- **Model:** Meta Llama vision through any OpenAI-compatible endpoint. Set `LLAMA_API_KEY`, `LLAMA_BASE_URL` and `LLAMA_MODEL`. The default is Meta's Llama API with Llama 4 Maverick.
- **Prompt and schema:** `vision.PROMPT` and `vision.SCHEMA` ask for 5–15 tags covering content and vibe. Prompt quality is the biggest lever here.
- **Parsing:** `vision.parse_reply` is tolerant of code fences and junk. An unreadable reply counts that screenshot as noise.
- **Testing without a key:** `POST /feeds` also takes `tags` as JSON, which skips Llama.

Ideas worth trying:
- One Llama call per screenshot vs. batching several images.
- Asking for separate "content" and "mood" tag lists with different weights.
- Dropping near-duplicate tags.
- Weighting screenshots by recency.

## Piece B: movie taste embedding → recommendations

**Offline build:** `scripts/build_catalog.py --genome-dir ml-32m --top 5000` (MovieLens tag genome), or `--tags-csv file.csv` (columns `movie_id,title,tag,weight`). This writes the two catalog files. It needs the real encoder, so run it on a laptop with `sentence-transformers` installed.

**Serving:** `GET /feeds/{id}/recs`:
1. `recommend.score_feed(model, x, cat.vecs)` → a score per film.
2. `recommend.pick(scores, exclude=already_rated)` → the top 8, plus 2 random picks from ranks 11–50 tucked in below the top 2. Each item records its `rank` and `explore` flag in the `recs` table.
3. `recommend.because_of(model, tags, t_m)` → the feed tags with the biggest contribution $w_i\,(W E(s_i)) \cdot t_m$.

Each response item looks like `{rec_id, id, title, year, tmdb_id, tags, score, because_of}`. Use `tmdb_id` for posters.

Ideas worth trying:
- `--tags-per-movie` (default 20).
- A popularity floor or boost.
- Dedupe by franchise.
- Diversity, for example MMR so the list isn't 10 versions of the same vibe.
- A smarter exploration policy.

**Don't change** how exploration picks are logged (`rank`, `explore`). Training and future evaluation depend on it.

## Piece C: W and training (Ryan)

- **`model.py`:** `Translator`, `scores`, `taste_target`, `loss_fn`, `recall_at_k`.
- **`trainer.py`:** `build_dataset()` turns SQLite events into `feeds` / `train` / `holdout`; `retrain()` runs one round with gate and hot-swap; the background thread is woken by `notify_event()`.
- **Knobs** live in `config.py` (rank, τ, λ, β, learning rate, steps, retrain interval, recall k), and all of them can be overridden with env vars.
- **Feedback labels:** `love`, `seen_loved` and `favourite` are positives; `nah` is a negative. `favourite` events with `split="holdout"` are never trained on.

## Endpoints at a glance

| Method | Path | Used by |
|---|---|---|
| `POST` | `/feeds` | A (screenshots or `tags` JSON) → `feed_id` |
| `POST` | `/feeds/{id}/favourites` | C (seed known loves, a share hidden for eval) |
| `GET` | `/feeds/{id}/recs` | B (10 recs) |
| `POST` | `/feedback` | everyone (`rec_id` + `love` / `seen_loved` / `nah`) |
| `POST` | `/admin/retrain`, `GET` `/model` | C (force a round, recall history for the demo chart) |
| `GET` | `/movies/search?q=`, `/health` | frontend |

## Running and testing

```bash
cd backend
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt
pytest -q                                  # fake hashing encoder + synthetic catalog, no keys needed
TANDEM_FAKE_ENCODER=1 uvicorn tandem.api:app --reload   # offline dev without model weights
```

The main test (`test_api_round_trip_and_live_training`) is the best executable spec of the whole loop. In it, gym-feed users like underdog films that share no words with their tags, and one retrain takes a new gym user's held-out recall@50 from 0 to 1.
