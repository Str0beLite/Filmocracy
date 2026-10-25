# Self-hosting Filmocracy

| Part | Address | Runs on | Deploys |
|---|---|---|---|
| Frontend | `https://filmocracy.party` | Cloudflare Pages | Pages builds every push to `main` |
| Backend | `https://api.filmocracy.party` | Your machine, behind a Cloudflare Tunnel | A timer pulls `main` every minute and restarts the API when it changed |

You don't need open ports, TLS setup or a GitHub runner. The repo is public, so a self-hosted runner would let forks run code on your machine. The machine has to stay on and awake while the app is live. While it's off, the frontend still loads but nothing works.

Sign-in is a plain user id. Each browser makes up a random id on its first visit, keeps it in `localStorage` and sends it as `Authorization: Bearer <id>`. There are no accounts, and anyone who learns an id can act as that user.

## Backend: one-time setup

Requires: Linux with systemd, Python 3.12, `filmocracy.party` in your Cloudflare account, and a filled-in `backend/.env` (`MUSE_API_KEY`; optionally `YOUTUBE_API_KEY`, which drops blocked or private trailers. Without it, catalog trailers are trusted as-is).

**1. cloudflared and the tunnel**

```bash
curl -fsSL -o ~/.local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x ~/.local/bin/cloudflared
cloudflared tunnel login                                      # browser: pick filmocracy.party
cloudflared tunnel create filmocracy                          # writes ~/.cloudflared/<TUNNEL_ID>.json
cloudflared tunnel route dns filmocracy api.filmocracy.party  # CNAME api -> the tunnel
```

Then write `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/<you>/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: api.filmocracy.party
    service: http://localhost:8000
  - service: http_status:404
```

WebSockets (`wss://api.filmocracy.party/sessions/<id>/ws`) pass through without extra config.

**2. Install the services**

Stop any dev server on port 8000 first, then run:

```bash
deploy/selfhost/install.sh
```

This takes a few minutes the first time, mostly installing torch. It does the following:
- Clones the repo to `~/filmocracy-live`. That copy is deploy-only, so keep working in your normal checkout.
- Creates the clone's own venv.
- Fills `~/.config/filmocracy/backend.env` with every key from a keys file. The default is `backend/.env`, or pass a path: `install.sh path/to/keys.env`.
  - Keys already in the production file are kept.
  - `TANDEM_DEV_AUTH`, `TANDEM_DATA_DIR`, `FRONTEND_ORIGINS` and `GOOGLE_CLIENT_ID` are never copied. It sets `TANDEM_DATA_DIR` and `FRONTEND_ORIGINS` itself.
  - It warns if `MUSE_API_KEY` or `YOUTUBE_API_KEY` is missing.
  - To change a key later, edit that file and run `systemctl --user restart filmocracy-api`.
- Installs three systemd user units from `deploy/selfhost/`:

| Unit | What it does |
|---|---|
| `filmocracy-api` | `uvicorn unified:app` on `127.0.0.1:8000` |
| `filmocracy-tunnel` | `cloudflared tunnel run filmocracy` |
| `filmocracy-deploy.timer` | Every minute, runs `update.sh`: if `origin/main` moved, it resets the clone to it, reinstalls requirements if they changed, and restarts the API |

- Enables lingering, so the services keep running when you log out.

Data (SQLite, W checkpoints) lives in `~/.local/share/filmocracy/`. Back it up by copying that folder while the API is stopped.

**Check it**

```bash
curl https://api.filmocracy.party/health
systemctl --user status filmocracy-api filmocracy-tunnel filmocracy-deploy.timer
journalctl --user -u filmocracy-api -f      # API logs
journalctl --user -u filmocracy-deploy      # "deployed <sha>" after each push
```

## Moving to a new host

`~/.config/filmocracy/backend.env` holds every production key, so it's the one file to carry over. Never commit it.

1. On the new host, clone the repo and install cloudflared (step 1 above, just the download).
2. Copy these over from the old host:
   - `~/.config/filmocracy/backend.env`: the keys.
   - `~/.cloudflared/`: the same tunnel, so DNS stays as it is. In `config.yml`, fix the `credentials-file` path if your home folder differs.
   - `~/.local/share/filmocracy/`, optionally: the votes and trained W. Copy it while the old API is stopped.
3. Stop the old host's services: `systemctl --user disable --now filmocracy-api filmocracy-tunnel filmocracy-deploy.timer`.
4. On the new host, run `deploy/selfhost/install.sh ~/.config/filmocracy/backend.env`.

## Frontend: Cloudflare Pages (one-time setup)

1. In the Cloudflare dashboard, go to **Workers & Pages**, then **Create**, then **Pages**, then **Connect to Git**, and pick `Str0beLite/Filmocracy`. Set the production branch to `main`.
2. Use these build settings: root directory `frontend`, build command `npm run build`, output directory `dist`.
3. Set the environment variable `VITE_TMDB_TOKEN=<TMDB read token>`. `VITE_API_URL` comes from the committed `frontend/.env.production`.
4. After the first build, go to **Custom domains** and add `filmocracy.party`. Cloudflare creates the DNS record.

From then on, every push to `main` redeploys the frontend, and the timer redeploys the backend within about a minute.

## Quick test without a domain

```bash
cloudflared tunnel --url http://localhost:8000
```

This prints a random `https://<words>.trycloudflare.com` URL. You don't need a login, and the URL changes every time you run it. Point `VITE_API_URL` at it and add the frontend's origin to `FRONTEND_ORIGINS`.
