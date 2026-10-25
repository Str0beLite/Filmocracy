#!/usr/bin/env bash
# One-time setup on the host machine: a deploy-only clone, its venv, the production env file and the systemd user units.
# Usage: install.sh [keys-file]   (keys-file defaults to backend/.env; on a new host pass your old ~/.config/filmocracy/backend.env)
# Safe to re-run. Needs `cloudflared tunnel login` + the tunnel and ~/.cloudflared/config.yml first (docs/self-hosting.md).
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
live=$HOME/filmocracy-live
venv=$live/backend/.venv

[ -d "$live/.git" ] || git clone -q https://github.com/Str0beLite/Filmocracy.git "$live"
if [ ! -x "$venv/bin/uvicorn" ]; then
  python3 -m venv "$venv"
  "$venv/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cpu
  "$venv/bin/pip" install -q -r "$live/backend/requirements.txt"
fi

mkdir -p ~/.config/filmocracy ~/.local/share/filmocracy ~/.config/systemd/user
env=~/.config/filmocracy/backend.env
touch "$env" && chmod 600 "$env"
# Copy in every key from the keys file (default: backend/.env) that the production file doesn't have yet.
# Existing production values win; dev-only and per-machine settings are never copied.
keys=${1:-$repo/backend/.env}
if [ -f "$keys" ]; then
  while IFS= read -r line; do
    k=${line%%=*}
    case $k in TANDEM_DEV_AUTH|TANDEM_DATA_DIR|FRONTEND_ORIGINS|GOOGLE_CLIENT_ID) continue ;; esac
    grep -q "^$k=" "$env" || printf '%s\n' "$line" >> "$env"
  done < <(grep -E '^[A-Z_][A-Z0-9_]*=.' "$keys")
else
  echo "warning: no keys file at $keys; add keys to $env by hand" >&2
fi
sed -i '/^TANDEM_DATA_DIR=/d' "$env"   # per machine: a file copied from another host may carry its path
echo "TANDEM_DATA_DIR=$HOME/.local/share/filmocracy" >> "$env"
grep -q '^FRONTEND_ORIGINS=' "$env" || echo 'FRONTEND_ORIGINS=https://filmocracy.party,http://localhost:5173' >> "$env"
for k in MUSE_API_KEY YOUTUBE_API_KEY; do grep -q "^$k=." "$env" || echo "warning: $k is not set in $env" >&2; done

cp "$repo"/deploy/selfhost/*.service "$repo"/deploy/selfhost/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable filmocracy-api filmocracy-tunnel filmocracy-deploy.timer
systemctl --user restart filmocracy-api filmocracy-tunnel filmocracy-deploy.timer   # pick up env changes on re-runs
loginctl enable-linger "$USER"   # keep the services running when you're logged out
systemctl --user --no-pager status filmocracy-api filmocracy-tunnel filmocracy-deploy.timer | grep -E '●|Active'
