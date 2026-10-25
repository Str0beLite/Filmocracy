"""All knobs in one place. Override any of them with env vars."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name, default, cast=str):
    return cast(os.environ.get(name, default))


# Where the movie catalog lives (built once by scripts/build_catalog.py, committed to git).
CATALOG_DIR = Path(_env("TANDEM_CATALOG_DIR", ROOT / "catalog"))
# Where runtime state lives (SQLite log + W checkpoints). On Railway, mount a volume here.
DATA_DIR = Path(_env("TANDEM_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "tandem.db"
CKPT_DIR = DATA_DIR / "checkpoints"

# Frozen text encoder. Set TANDEM_FAKE_ENCODER=1 to use a hashing stand-in (tests, offline dev).
EMBED_MODEL = _env("TANDEM_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
FAKE_ENCODER = _env("TANDEM_FAKE_ENCODER", "0") == "1"
DIM = 384

# Claude model that writes taste profiles (bulk, cheap, vision-capable).
PROFILE_MODEL = _env("TANDEM_PROFILE_MODEL", "claude-haiku-5-5")

# Translator W = I + A Bᵀ and its training.
RANK = _env("TANDEM_RANK", 8, int)
TAU = _env("TANDEM_TAU", 0.05, float)
LAMBDA = _env("TANDEM_LAMBDA", 1e-3, float)       # pulls W back toward identity (zero-shot)
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
MIN_VOTES = _env("TANDEM_MIN_VOTES", 500, int)  # don't recommend obscure films

POSITIVE_LABELS = {"love", "seen_loved", "favourite"}
NEGATIVE_LABELS = {"nah"}
