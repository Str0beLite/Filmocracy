# Decisions

One line each: date, decision, why.

- 2026-10-24: Demo UI is a no-build React page (React 18 from a CDN, JSX compiled by in-browser Babel) in `frontend/demo`, served with `python -m http.server`. The local Node is 14.17, too old for Vite, and this needs no install.
- 2026-10-24: The demo fakes the group in one browser tab (three scripted friends, scripted votes). No backend or real-time sync yet.
- 2026-10-24: Three candidate looks (Velvet, Neon, Matinee) are CSS token sets switchable from the demo toolbar. Pick one before building the real app.
- 2026-10-24: Only the big screen moves the night forward (start, skip, picks, start movie). Phones join, react and vote, then wait with instructions.
- 2026-10-24: Dropped the per-person "movie vibe" card; each person picks how they want to feel tonight instead, and it shows on their seat.
- 2026-10-24: The night ends on a top 3 (golden buzzers first, then by votes, then by prediction) plus 5 predicted recs.
- 2026-10-24: Progress shows as a "completion status" loading bar in the big screen's top-right, not as a model confidence score.
- 2026-10-24: Votes are private. Screens show who has voted and whether it was unanimous, never who said yes or no (no per-seat reveal, no counts).
