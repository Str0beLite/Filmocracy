# Frontend

The Tandem app: the big screen (TV, laptop, projector) and the phone, in the Velvet look. Vite + React + TypeScript.

**This pass is frontend only.** Every screen is real, but buttons only move to the next page and the data is mock. Nothing talks to the backend yet.

## Run it

Needs Node 20.19 or newer (Node 24 LTS on the team laptop). From the repo root:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Open http://localhost:5173. In dev, that page lists every screen.

- **Big screen:** open http://localhost:5173/tv/lobby on the laptop or TV, fullscreen it (F11).
- **Phones:** must be on the same Wi-Fi as the laptop. Scan the QR code in the lobby, or the one on the index page. The dev server listens on the network and the QR code points at the laptop's Wi-Fi address, even when the TV page is open on localhost.
- **Stepping through:** the arrows on the right edge of every screen (dev only) go to the next or previous screen, including the phone screens that would normally wait on the big screen.

Other commands: `npm run build` (type-check + production build), `npm run lint`, `npm run preview`.

## How a night flows

| Big screen | Phone |
|---|---|
| `/tv/lobby`: QR code, seats, Start the show | `/phone/join` → `sign-in` → `feeling` → `screenshots` (3 Explore screenshots) → `reading` → `lobby` (waits) |
| `/tv/trailer/:n` (auto-advances when it ends, or Skip to vote) | `/phone/react/:n`: emotes |
| `/tv/vote/:n` → `/tv/reveal/:n` | `/phone/vote/:n` → `/phone/voted/:n` |
| `/tv/buzzer/:n`: everyone said yes (picks or keep browsing) | `/phone/buzzer/:n` |
| `/tv/miss/:n`, then the next trailer | `/phone/miss/:n` |
| `/tv/checkpoint/:n`: every 5 trailers without a buzzer, picks or keep watching | `/phone/checkpoint/:n` |
| `/tv/picks`: top 3 + 5 more, Start #1 | `/phone/picks` |
| `/tv/showing/:id` | `/phone/showing/:id` |

Votes stay private: screens show who has voted, never how.

The mock night is scripted in `src/api/mock.ts`: trailer 2 is a golden buzzer, and trailers 1 and 3–5 miss, so trailer 5 reaches the checkpoint.

## Where things live

| Path | What |
|---|---|
| `src/api/index.ts` | **The only place screens get data from.** Reads `mock.ts` today; wiring the backend means swapping these function bodies for fetches. |
| `src/api/types.ts` | `Rec` matches the backend's rec shape; the rest is what screens need. |
| `src/api/mock.ts` | Mock room, people, feelings (with the catalog tags each one boosts), trailers and picks. Films and ids are real rows from `backend/catalog/movies.json`. |
| `src/router.tsx` | One URL per screen; loaders call `src/api`. |
| `src/tv/`, `src/phone/` | Big-screen and phone screens. |
| `src/components/ui.tsx` | Seats, posters, QR, completion bar, confetti. |
| `src/lib/` | Night rules (checkpoint, completion bar), next-screen flow, GSAP helpers. |
| `src/styles/` | `base.css` holds the Velvet tokens; `tv.css` and `phone.css` the screens. |
| `demo/` | The original clickable demo (all three looks), kept as a reference. `python -m http.server 5174 --directory frontend/demo` |

## Not wired yet

These come with the backend (see `docs/decisions.md`): a sessions module that runs the night over WebSockets, Google sign-in (dev login locally), uploading screenshots to `POST /feeds`, re-ranking group recs after every vote, sending tonight's feelings as tag boosts, and TMDB posters and trailers by `tmdb_id`. Posters and trailers are generated placeholder art until then.

`.env.example` lists the env vars the wired-up app will need.
