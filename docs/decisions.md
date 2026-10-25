# Decisions

One line each: date, decision, why.

- 2026-10-24: Demo UI is a no-build React page (React 18 from a CDN, JSX compiled by in-browser Babel) in `frontend/demo`, served with `python -m http.server`. The local Node is 14.17, too old for Vite, and this needs no install.
- 2026-10-24: The demo fakes the group in one browser tab (three scripted friends, scripted votes). No backend or real-time sync yet.
- 2026-10-24: Three candidate looks (Velvet, Neon, Matinee) are CSS token sets switchable from the demo toolbar. Pick one before building the real app.
