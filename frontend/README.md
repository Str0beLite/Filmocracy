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
2. Pick how you want to feel tonight, then type a name and **Continue with Instagram**. The phone takes your seat on its own.
3. From here the phone only waits, reacts and votes. Everything that moves the night forward is on the big screen: **Start the show**, **Skip to vote**, **See tonight's picks**, **Start #1**.
4. Tap emotes on the phone while the trailer plays; they float up from your seat on the big screen.
5. Vote. Votes stay private: screens only show who has locked in, then either the golden buzzer or "Not this one." The first trailer is scripted to miss; vote yes on the second for the golden buzzer.
6. The night ends on the group's top 3 plus 5 more predicted picks. If nobody hits the golden buzzer, it lands there after the last trailer.

The **completion status** bar in the big screen's top-right corner is a loading bar for "how close are we to tonight's movie", not a model score. It's faked in `engine.jsx` (`completionStatus`): seating everyone fills 30%, votes and rounds push it up, and it hits 100% at a golden buzzer or the final picks.

The toolbar switches between three looks (Velvet, Neon, Matinee) and restarts.

### Where things live

| File | What |
|---|---|
| `data.js` | Friends, moods, movies, scripted votes, the 5 predicted recs, Instagram "signals" and copy. Edit this to change the demo. |
| `engine.jsx` | The scripted movie night: phases, timers, fake friends, completion status, pick ranking. |
| `tv.jsx` | Big screen: lobby with QR, trailer, verdict, golden buzzer, top picks, now showing. |
| `phone.jsx` | Phone: scan, tonight's feeling, connect Instagram, waiting screen, emotes, vote, results, picks. |
| `shared.jsx` | Seats, avatars, posters, QR, confetti, completion bar, icons. |
| `styles.css` | All styling. The three looks are token sets at the top of the file. |

Trailers and posters are placeholder art generated from each movie's colors; there's no real video yet.
