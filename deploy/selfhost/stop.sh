#!/usr/bin/env bash
# Stop the backend however it's running: the background services, a start.sh terminal, or both.
set -uo pipefail
systemctl --user stop filmocracy-deploy.timer filmocracy-api filmocracy-tunnel
pidfile=$HOME/.local/state/filmocracy-start.pid
if [ -f "$pidfile" ] && kill "$(cat "$pidfile")" 2>/dev/null; then
  echo "stopped start.sh"   # its trap takes the API and tunnel down with it
fi
rm -f "$pidfile"
echo "backend stopped; start again with deploy/selfhost/start.sh or systemctl --user start filmocracy-api filmocracy-tunnel filmocracy-deploy.timer"
