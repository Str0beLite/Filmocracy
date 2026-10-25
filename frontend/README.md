# Frontend

The Filmocracy app: the big screen (TV, laptop, projector) and the phone, in the Velvet look. Vite + React + TypeScript.

**It runs on the real backend** (`backend/unified.py`, see [the unified backend guide](../docs/unified-backend.md)). The TV creates a session and shows its invitation as a QR code; phones sign in, join, upload Explore screenshots (read by Muse Spark) and vote. The backend picks trailers with the recommendation model, counts votes and ranks the picks. The TV runs the night around that (trailer, vote, verdict, picks) and publishes it as the session's *stage*, so every phone follows along over the WebSocket.

## Run it

Needs Node 20.19 or newer (Node 24 LTS on the team laptop) and the backend's Python environment (see `backend/README.md`). From the repo root, in two terminals:

```bash
# 1. Backend on :8000. backend/.env needs MUSE_API_KEY, YOUTUBE_API_KEY,
#    TANDEM_DEV_AUTH=1 for local sign-in, and FRONTEND_ORIGINS listing http://localhost:5173
#    and the laptop's Wi-Fi address (http://<ip>:5173) so phones can open the WebSocket.
backend/.venv/bin/uvicorn unified:app --app-dir backend --env-file backend/.env --host 0.0.0.0 --port 8000

# 2. Frontend on :5173. It forwards /api (and the WebSocket) to the backend.
npm --prefix frontend install
npm --prefix frontend run dev
```

Sign-in is a random user id each browser keeps (`src/api/auth.ts`). Put `VITE_DEV_AUTH=1` in `frontend/.env.local` to give each phone tab its own id, so one laptop can play a whole group.

1. On the laptop, open http://localhost:5173/tv and fullscreen it (F11). Put it on the TV or projector.
2. Everyone scans the QR code with a phone on the **same Wi-Fi**. The QR points at the laptop's Wi-Fi address even when the TV page is on localhost.
3. Each phone signs in, picks a feeling, adds 1–3 Explore screenshots (one is enough; more steadies the picks. Muse reads every tile, which takes a few seconds), and takes a seat.
4. Start the show from the big screen.

Dev-only controls on the right edge: the TV's fast-forward ends the trailer, then closes voting as it stands, then moves on; the phone's leave button leaves the session.

**Trailers:** the backend only queues films whose YouTube trailer it has checked, and the TV plays that trailer to the end, then opens voting. `VITE_TMDB_TOKEN` is a fallback lookup by `tmdb_id` (`src/api/tmdb.ts`).

Other commands: `npm run build` (type-check + production build), `npm run lint`, `npm run preview`.

## How a night flows

| Big screen | Phone |
|---|---|
| `/tv/lobby`: QR code, seats fill as phones join, Start the show | `/phone/join` → `sign-in` → `name` → `feeling` → `screenshots` → `reading` → `lobby` (waits) |
| `/tv/trailer/:n`: the whole trailer (12 s of placeholder art without one), or Skip to vote | `/phone/react/:n`: reactions float up from your seat on the TV |
| `/tv/vote/:n` → `/tv/reveal/:n` | `/phone/vote/:n` → `/phone/voted/:n` |
| `/tv/buzzer/:n`: everyone said yes; picks or keep browsing | `/phone/buzzer/:n` |
| `/tv/miss/:n`, then the next trailer on its own | `/phone/miss/:n` |
| `/tv/checkpoint/:n`: every 5 trailers without a buzzer; picks or keep watching | `/phone/checkpoint/:n` |
| `/tv/picks`: top 3 + 5 more, Start #1 | `/phone/picks` |
| `/tv/showing/:id`, then New night, same crew | `/phone/showing/:id` |

Votes stay private: the server never sends how anyone voted, only who has voted and whether it was unanimous. Each phone remembers its own vote. Voting closes by itself after 60 s, so a phone that fell asleep can't stall the night.

## Where things live

| Path | What |
|---|---|
| `src/api/index.ts` | **The only place screens talk to the backend**: `connect()` follows the session's WebSocket and builds a `Snapshot`, `act()` maps each screen action to a backend call, `movie()` reads `/session-catalog`. On the TV it also runs the night and publishes the stage. |
| `src/api/auth.ts` | The bearer token: a random user id kept in the browser (per tab for phones when `VITE_DEV_AUTH=1`). |
| `src/api/types.ts` | `Snapshot` is what every screen sees; `Rec` matches the Python backend's rec shape. |
| `src/api/data.ts` | Seat colours, feelings and the catalog tags each one boosts, reactions, generated poster art. |
| `src/api/tmdb.ts` | Trailer lookup: TMDB's videos for a `tmdb_id`, official YouTube trailer first. |
| `src/room/` | `RoomProvider` keeps the live snapshot; `useRoom()` reads it. |
| `src/lib/flow.ts` | Which screen each device should be on for the room's state. |
| `src/tv/`, `src/phone/` | Big-screen and phone screens. |
| `src/components/ui.tsx` | Seats, posters, QR, completion bar, confetti, action buttons. |
| `src/styles/` | `base.css` holds the Velvet tokens; `tv.css` and `phone.css` the screens. |
| `demo/` | The original clickable demo (all three looks), kept as a reference. `python -m http.server 5174 --directory frontend/demo` |

## Not wired yet

- **Feelings don't steer the picks yet.** They're saved and shown on seats, but the session queue (`backend/session_recommendations.py`) takes no tag boosts.
- **"Why it's here" and match %** during trailers: the queue doesn't return per-feed reasons or scores. Picks show match % from the final ranking.
- Posters are generated art; the catalog's `poster_url` isn't used yet.

`.env.example` lists the env vars the app needs. `session-client.js` is the backend team's standalone WebSocket helper (`node --test frontend/session-client.test.mjs`); the app uses its own client in `src/api/index.ts`.
