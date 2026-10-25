# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Vite + React + TypeScript in `frontend/` (Node 22 LTS), React Router, GSAP via `@gsap/react` for big moments only. Backend is the FastAPI service in `backend/`. First app pass is frontend only, with typed mock data behind `src/api`.

## Users

Established friend groups watching a movie together in one room, usually a dim living room at night. One person's laptop, TV, iPad or projector is the big screen; everyone else uses their own phone.

## Product Purpose

Filmocracy picks a movie the whole group will say yes to, and ends the "what do you want to watch?" argument. Success is the group landing on a film quickly, and enjoying it.

## Positioning

- Taste comes from each person's Instagram Explore screenshots, not from rating movies.
- One shared model learns from every group vote, so recommendations get sharper over time.
- It aims past the obvious pick: films the group might not have chosen themselves but will surprisingly enjoy together.

## Operating Context

- Big screen shows a QR code; phones scan to join, sign in with Google, say how they want to feel tonight, and upload 3 Explore screenshots once.
- Trailers play on the big screen; phones react with emotes and vote yes/no. Only the big screen moves the night forward.
- Golden buzzer when everyone votes yes. Every 5 trailers without one, the big screen offers "See our picks" or "Keep watching".
- The night ends on the group's top 3 plus 5 more predicted recs. A completion status bar shows progress toward a pick.

## Capabilities and Constraints

- Votes are private: screens show who has voted and whether it was unanimous, never who said yes or no.
- The big screen is read from a sofa: large type, high contrast, little text.
- Phones are used one-handed in the dark.
- Posters and trailers are generated placeholders until TMDB is wired in.

## Brand Commitments

- Name: Filmocracy.
- Voice: warm, playful-confident, short sentences, no jargon on screen.
- Look: "Velvet" from `frontend/demo` (the chosen of three demo looks).

## Evidence on Hand

No real users, testimonials or metrics yet. Don't invent any. Movie catalog: 5000 MovieLens films in `backend/catalog/movies.json`.

## Product Principles

- The room is the user: design for the group on the sofa, not one person at a desk.
- The big screen leads, phones follow.
- Privacy keeps it friendly: nobody gets called out for a no.
- Surprise over safe: show why a less obvious pick fits.
- Zero homework: no forms or ratings beyond the three screenshots and one feeling.

## Accessibility & Inclusion

Readable at TV distance; usable one-handed on a phone in the dark; honours reduced motion.
