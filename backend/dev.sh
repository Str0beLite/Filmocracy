#!/usr/bin/env bash
# Local backend for frontend development: sets up the venv and backend/.env on first run, then serves with --reload.
# Usage: backend/dev.sh [port]   (default 8000; data goes to backend/data, never the live database)
# Then: npm --prefix frontend run dev   (with another port: TANDEM_BACKEND=http://localhost:<port> npm --prefix frontend run dev)
set -euo pipefail
cd "$(dirname "$0")"
port=${1:-8000}
if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu
  .venv/bin/pip install -q -r requirements.txt
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "created backend/.env; add MUSE_API_KEY to read screenshots (optional: YOUTUBE_API_KEY)" >&2
fi
exec .venv/bin/uvicorn unified:app --env-file .env --host 0.0.0.0 --port "$port" --reload
