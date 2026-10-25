"""All knobs in one place. Override any of them with env vars."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name, default, cast=str):
    return cast(os.environ.get(name, default))


# Movie catalog with each film's tags + tag-embedding vector (built once by scripts/build_catalog.py, committed).
CATALOG_DIR = Path(_env("TANDEM_CATALOG_DIR", ROOT / "catalog"))
# Pre-trained W a fresh database starts from (scripts/seed_fake.py + real ratings). Delete it to start at W = I.
SEED_W = Path(_env("TANDEM_SEED_W", CATALOG_DIR / "w_seed.pt"))
# Runtime state (SQLite log + W checkpoints). On Railway, mount a volume here.
DATA_DIR = Path(_env("TANDEM_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "tandem.db"
CKPT_DIR = DATA_DIR / "checkpoints"

# Frozen tag encoder (a small sentence model, not an LLM). TANDEM_FAKE_ENCODER=1 = hashing stand-in for tests.
EMBED_MODEL = _env("TANDEM_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
FAKE_ENCODER = _env("TANDEM_FAKE_ENCODER", "0") == "1"
DIM = 384
TAGS_PER_MOVIE = _env("TANDEM_TAGS_PER_MOVIE", 20, int)   # strongest tags kept per film when building

# Meta Muse Spark reads each Explore tile into free-form tags, over the Meta Model API (OpenAI-compatible
# Chat Completions). Any other OpenAI-compatible vision endpoint works if you override these.
MUSE_BASE_URL = _env("MUSE_BASE_URL", "https://api.meta.ai/v1")
MUSE_MODEL = _env("MUSE_MODEL", "muse-spark-1.3")
MUSE_API_KEY_ENV = "MUSE_API_KEY"
# Muse Spark thinks before answering; thinking counts against max_tokens, so leave room for it.
MUSE_REASONING = _env("MUSE_REASONING", "minimal")   # minimal | low | medium | high; "" = model default
MUSE_MAX_TOKENS = _env("MUSE_MAX_TOKENS", 4096, int)

# Translator W = I + A Bᵀ (DIM × DIM) and its training.
RANK = _env("TANDEM_RANK", 8, int)
TAU = _env("TANDEM_TAU", 0.05, float)
LAMBDA = _env("TANDEM_LAMBDA", 1e-3, float)       # pulls W back toward identity (zero-shot)
BETA = _env("TANDEM_BETA", 1.0, float)            # weight of "hit the user's film-taste vector"
LR = _env("TANDEM_LR", 1e-2, float)
TRAIN_STEPS = _env("TANDEM_TRAIN_STEPS", 100, int)
HARD_NEG_WEIGHT = _env("TANDEM_HARD_NEG_WEIGHT", 5.0, float)
RETRAIN_EVERY = _env("TANDEM_RETRAIN_EVERY", 20, int)  # new feedback events between retrains
RECALL_K = _env("TANDEM_RECALL_K", 50, int)
HOLDOUT_NEWEST_FRAC = 0.10

# Serving.
N_RECS = 10
N_EXPLORE = 2
EXPLORE_RANKS = (10, 50)   # exploration picks come from ranks 11–50

POSITIVE_LABELS = {"love", "seen_loved", "favourite"}
NEGATIVE_LABELS = {"nah"}
TAG_BOOST = _env("TANDEM_TAG_BOOST", 0.15, float)   # added to films carrying any tag the host asked to boost
POP_INIT = _env("TANDEM_POP_INIT", 0.05, float)     # starting weight on the popularity prior; training learns it from there
VOTE_PULL = _env("TANDEM_VOTE_PULL", 0.1, float)    # each vote (up to 10) pulls the taste this far toward loved films, before any retrain

# Auth: Google ID tokens must be issued for this OAuth client. Admin endpoints need X-Admin-Token.
GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID", "")
ADMIN_TOKEN = _env("TANDEM_ADMIN_TOKEN", "")
# Local dev only: `Bearer <name>` signs in as <name> with no Google check. Never set this in production.
DEV_AUTH = _env("TANDEM_DEV_AUTH", "0") == "1"
