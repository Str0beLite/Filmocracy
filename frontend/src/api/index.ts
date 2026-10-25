// The one place screens get data from. Today it reads mock.ts; wiring the
// backend means swapping these bodies for fetches (backend/README.md, "API")
// plus TMDB lookups by tmdb_id. Screens don't change.

import { DETAILS, EMOTES, FEELINGS, ME_ID, MY_FEED_TAGS, OUTCOMES, PEOPLE, PREDICTED, ROOM, TRAILERS } from './mock';
import type { Movie, Picks, Rec, Room, Round } from './types';

export type * from './types';
export { EMOTES, FEELINGS, ME_ID };

// Backend scores run ~0 (median) to ~0.3 (top); this is a display scale only.
const toMatch = (score: number) => Math.min(99, Math.round(50 + score * 160));

function toMovie(r: Rec): Movie {
  const { why, ...details } = DETAILS[r.id];
  return {
    ...details,
    id: r.id,
    tmdbId: r.tmdb_id,
    title: r.title,
    year: r.year,
    match: toMatch(r.score),
    wildcard: Boolean(r.explore),
    why,
  };
}

export async function getRoom(): Promise<Room> {
  return { ...ROOM, people: PEOPLE };
}

export async function getRound(n: number): Promise<Round> {
  const i = (Math.max(1, n) - 1) % TRAILERS.length;
  return { n, movie: toMovie(TRAILERS[i]), outcome: OUTCOMES[i] };
}

export async function getRounds(from: number, to: number): Promise<Round[]> {
  const ns = Array.from({ length: to - from + 1 }, (_, k) => from + k);
  return Promise.all(ns.map(getRound));
}

// Golden buzzers first, then the trailers people liked, then predictions.
export async function getPicks(): Promise<Picks> {
  const movies = [...TRAILERS, ...PREDICTED].map(toMovie);
  const byId = (id: number) => movies.find((m) => m.id === id)!;
  return {
    top: [
      { movie: byId(195159), source: 'buzzer' },
      { movie: byId(152970), source: 'trailers' },
      { movie: byId(164179), source: 'predicted' },
    ],
    more: PREDICTED.slice(1).map(toMovie),
  };
}

// POST /feeds returns the tags it read from the screenshots.
export async function getMyFeedTags(): Promise<string[]> {
  return MY_FEED_TAGS;
}
