#!/usr/bin/env bash
# Pull origin/main into the live clone (and its requirements). Run every minute by filmocracy-deploy.timer, or by hand.
# Restarts the background service if it's running; if you use start.sh instead, Ctrl+C it and start it again.
set -euo pipefail
cd "$HOME/filmocracy-live"
git fetch -q origin main
old=$(git rev-parse HEAD)
if [ "$old" = "$(git rev-parse origin/main)" ]; then [ -t 1 ] && echo "already at $(git rev-parse --short HEAD)"; exit 0; fi
git reset -q --hard origin/main   # this clone is deploy-only; nobody edits it
if ! git diff --quiet "$old" HEAD -- backend/requirements.txt; then
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if ! git diff --quiet "$old" HEAD -- backend/catalog/movies.json; then
  # A new catalog moves the centre that feed vectors are measured from; rebuild them (idempotent).
  data=$(grep -m1 '^TANDEM_DATA_DIR=' "$HOME/.config/filmocracy/backend.env" | cut -d= -f2-)
  TANDEM_DATA_DIR=${data:-backend/data} PYTHONPATH=backend backend/.venv/bin/python backend/scripts/recenter_feeds.py
fi
echo "deployed $(git rev-parse --short HEAD)"
if systemctl --user is-active -q filmocracy-api; then
  systemctl --user restart filmocracy-api
else
  echo "restart start.sh to serve it"
fi
