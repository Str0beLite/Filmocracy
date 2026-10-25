# Frontend

The Tandem app: the big screen (TV, laptop, projector) and the phone, in the Velvet look. Vite + React + TypeScript.

**It runs on a fake backend for now.** A small in-memory room server (`mock-backend/`) runs inside the Vite dev server, so a real night works across the TV and everyone's phones: people join, pick feelings, react and vote, and the server counts votes, runs the timers and moves every screen together. Recommendations are a fixed list of 14 real catalog films, re-ranked by tonight's feelings and votes. The Python backend isn't involved yet.

## Run it

Needs Node 20.19 or newer (Node 24 LTS on the team laptop). From the repo root:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

1. On the laptop, open http://localhost:5173/tv and fullscreen it (F11). Put it on the TV or projector.
2. Everyone scans the QR code with a phone on the **same Wi-Fi**. The QR points at the laptop's Wi-Fi address even when the TV page is on localhost.
3. Each phone signs in (for now, "Sign in with Google" just asks for a first name), picks a feeling, adds 3 Explore screenshots, and takes a seat.
4. Start the show from the big screen.

http://localhost:5173 (dev only) shows the room, a phone QR code, and buttons to jump the room to any screen for review (empty seats get test friends Maya, Jordan and Sam), fill seats, start a new night or reset the room.

Dev-only controls on the right edge: the TV's fast-forward skips to the next step (missing votes count as yes); the phone's leave button forgets this phone's seat. Each browser tab is its own person, so you can test with a few tabs on one laptop.

**Real trailers:** put a TMDB API Read Access Token in `frontend/.env.local` as `VITE_TMDB_TOKEN` (see `.env.example`) and restart the dev server. The TV then plays each film's YouTube trailer to the end, looked up from TMDB by `tmdb_id` (`src/api/tmdb.ts`), and voting opens when it finishes. Without a token it shows placeholder art.

Other commands: `npm run build` (type-check + production build), `npm run lint`, `npm run preview` (no fake backend in preview).

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
| `mock-backend/index.ts` | The fake backend: one room, its timers, vote counting, the fake re-ranking and pick ranking. Clients POST actions to `/mock-api/<action>` and listen on `/mock-api/events` (Server-Sent Events). |
| `src/api/index.ts` | **The only place screens talk to the backend**: `connect()` for live snapshots, `act()` for actions, `movie()` for film details. The real session service should speak the same protocol. |
| `src/api/types.ts` | `Snapshot` is what every screen sees; `Rec` matches the Python backend's rec shape. |
| `src/api/mock.ts` | Films (real `movies.json` rows), placeholder details and art, feelings and the catalog tags each one boosts, fake feed tags. |
| `src/api/tmdb.ts` | Trailer lookup: TMDB's videos for a `tmdb_id`, official YouTube trailer first. |
| `src/room/` | `RoomProvider` keeps the live snapshot; `useRoom()` reads it. |
| `src/lib/flow.ts` | Which screen each device should be on for the room's state. |
| `src/tv/`, `src/phone/` | Big-screen and phone screens. |
| `src/components/ui.tsx` | Seats, posters, QR, completion bar, confetti, action buttons. |
| `src/styles/` | `base.css` holds the Velvet tokens; `tv.css` and `phone.css` the screens. |
| `demo/` | The original clickable demo (all three looks), kept as a reference. `python -m http.server 5174 --directory frontend/demo` |

## Not wired yet

These come with the real backend (see `docs/decisions.md`): the session service (replacing `mock-backend/`), Google sign-in, uploading screenshots to `POST /feeds` (the phone keeps them locally for now), real group recs from `POST /groups/{id}/recs` with feelings as tag boosts, sending votes to `POST /feedback`, and TMDB posters by `tmdb_id`. Posters are generated placeholder art until then.

`.env.example` lists the env vars the wired-up app will need.

## SQLite backend integration

The production session backend is documented in [the unified backend guide](../docs/unified-backend.md). `session-client.js` provides authenticated WebSocket snapshots and heartbeats; it is not yet wired into the app above. Run `node --test frontend/session-client.test.mjs` from the repository root.
