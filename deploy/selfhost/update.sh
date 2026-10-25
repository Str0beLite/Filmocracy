#!/usr/bin/env bash
# Pull origin/main into the live clone and restart the API if it changed. Run every minute by filmocracy-deploy.timer.
set -euo pipefail
cd "$HOME/filmocracy-live"
git fetch -q origin main
old=$(git rev-parse HEAD)
[ "$old" = "$(git rev-parse origin/main)" ] && exit 0
git reset -q --hard origin/main   # this clone is deploy-only; nobody edits it
if ! git diff --quiet "$old" HEAD -- backend/requirements.txt; then
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
systemctl --user restart filmocracy-api
echo "deployed $(git rev-parse --short HEAD)"
