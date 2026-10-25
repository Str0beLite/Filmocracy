#!/usr/bin/env bash
# One-time setup on the host machine: a deploy-only clone, its venv, the production env file and the systemd user units.
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
if [ ! -f "$env" ]; then
  # Keys come from your dev backend/.env; dev-only and per-machine settings are replaced.
  grep -vE '^(TANDEM_DEV_AUTH|TANDEM_DATA_DIR|FRONTEND_ORIGINS|GOOGLE_CLIENT_ID)=' "$repo/backend/.env" > "$env"
  printf 'TANDEM_DATA_DIR=%s\nFRONTEND_ORIGINS=https://filmocracy.party,http://localhost:5173\n' "$HOME/.local/share/filmocracy" >> "$env"
  chmod 600 "$env"
fi

cp "$repo"/deploy/selfhost/*.service "$repo"/deploy/selfhost/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now filmocracy-api filmocracy-tunnel filmocracy-deploy.timer
loginctl enable-linger "$USER"   # keep the services running when you're logged out
systemctl --user --no-pager status filmocracy-api filmocracy-tunnel filmocracy-deploy.timer | grep -E '●|Active'
