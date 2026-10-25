"""All knobs in one place. Override any of them with env vars."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name, default, cast=str):
    return cast(os.environ.get(name, default))


# Movie tag catalog + IG tag vocabulary + W prior (built once by scripts/build_catalog.py, committed).
CATALOG_DIR = Path(_env("TANDEM_CATALOG_DIR", ROOT / "catalog"))
# Runtime state (SQLite log + W checkpoints). On Railway, mount a volume here.
DATA_DIR = Path(_env("TANDEM_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "tandem.db"
CKPT_DIR = DATA_DIR / "checkpoints"

# Meta Llama vision model that turns a feed screenshot into an IG tag vector. Any OpenAI-compatible
# endpoint works: Meta's Llama API (default), Together, Groq, or a local Ollama (llama3.2-vision).
LLAMA_BASE_URL = _env("LLAMA_BASE_URL", "https://api.llama.com/compat/v1/")
LLAMA_MODEL = _env("LLAMA_MODEL", "Llama-4-Maverick-17B-128E-Instruct-FP8")
LLAMA_API_KEY_ENV = "LLAMA_API_KEY"

# Translator W = W0 + A Bᵀ (movie_tags × ig_tags) and its training.
RANK = _env("TANDEM_RANK", 8, int)
TAU = _env("TANDEM_TAU", 0.05, float)
LAMBDA = _env("TANDEM_LAMBDA", 1e-3, float)       # pulls W back toward the prior W0
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
