#!/usr/bin/env bash
# Run the API and the tunnel in this terminal, logs interleaved. Ctrl+C stops both.
# Usage: start.sh [code-dir]   (default ~/filmocracy-live; pass your checkout to serve unpushed code)
set -euo pipefail
dir=$(cd "${1:-$HOME/filmocracy-live}" && pwd)
venv=$dir/backend/.venv
[ -x "$venv/bin/uvicorn" ] || venv=$HOME/filmocracy-live/backend/.venv
cloudflared=$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")

if systemctl --user is-active -q filmocracy-api filmocracy-tunnel filmocracy-deploy.timer; then
  echo "The background services are running. Stop them first:" >&2
  echo "  systemctl --user stop filmocracy-deploy.timer filmocracy-api filmocracy-tunnel" >&2
  exit 1
fi

trap 'trap - EXIT INT TERM; kill 0' EXIT INT TERM   # take the other process down with whichever stops first
echo "serving $dir"
"$cloudflared" tunnel run filmocracy 2>&1 | sed -u 's/^/[tunnel] /' &
"$venv/bin/uvicorn" unified:app --app-dir "$dir/backend" --env-file "$HOME/.config/filmocracy/backend.env" \
  --host 127.0.0.1 --port 8000 2>&1 | sed -u 's/^/[api]    /' &
wait -n
