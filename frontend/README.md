# Frontend

## Demo UI (`demo/`)

A clickable prototype of the whole movie-night flow, used to nail down the look. The big screen and one phone sit side by side, and three fake friends (Maya, Jordan, Sam) join, react and vote on their own.

Run it from the repo root:

```bash
python -m http.server 5173 --directory frontend/demo
```

Then open http://localhost:5173. No install step: React, Babel and the QR library load from a CDN, so you need internet for the first load.

### Walkthrough

1. Click the QR code on the big screen (or **Scan** on the phone) to join.
2. Type a name, **Continue with Instagram**, then **Take my seat**.
3. **Start the show** once everyone is seated.
4. Tap emotes on the phone while the trailer plays; they float up from your seat on the big screen.
5. Vote. The first trailer is scripted to miss (Sam passes); vote yes on the second for the golden buzzer.

The toolbar switches between three looks (Velvet, Neon, Matinee), skips the trailer and restarts.

### Where things live

| File | What |
|---|---|
| `data.js` | Friends, movies, scripted votes, Instagram "signals" and copy. Edit this to change the demo. |
| `engine.jsx` | The scripted movie night: phases, timers, fake friends. |
| `tv.jsx` | Big screen: lobby with QR, trailer, verdict, golden buzzer, now showing. |
| `phone.jsx` | Phone: scan, connect Instagram, vibe card, lobby, emotes, vote, results. |
| `shared.jsx` | Seats, avatars, posters, QR, confetti, icons. |
| `styles.css` | All styling. The three looks are token sets at the top of the file. |

Trailers and posters are placeholder art generated from each movie's colors; there's no real video yet.
