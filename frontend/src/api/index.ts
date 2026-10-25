// The one place screens talk to the backend. Today that's the fake backend in
// mock-backend/ (served by the Vite dev server); the real session service
// should speak the same protocol: a stream of Snapshots plus POSTed actions.
// Movie details come from mock.ts until TMDB is wired in by tmdb_id.

import { CATALOG, DETAILS, EMOTES, FEELINGS } from './mock';
import type { Movie, Snapshot } from './types';

export type * from './types';
export * from './rules';
export { EMOTES, FEELINGS };

const BASE = '/mock-api';

// Backend scores run ~0 (median) to ~0.3 (top); this is a display scale only.
const toMatch = (score: number) => Math.min(99, Math.round(50 + score * 160));

const movies = new Map<number, Movie>(
  CATALOG.map((r) => [
    r.id,
    {
      ...DETAILS[r.id],
      id: r.id,
      tmdbId: r.tmdb_id,
      title: r.title,
      year: r.year,
      tags: r.tags,
      match: toMatch(r.score),
      wildcard: Boolean(r.explore),
    },
  ]),
);

export const movie = (id: number) => movies.get(id)!;

// Live room updates. Reconnects on its own (EventSource does) when a phone
// wakes up or the Wi-Fi blips.
export function connect(onSnapshot: (s: Snapshot) => void, onStatus: (online: boolean) => void) {
  const es = new EventSource(`${BASE}/events`);
  es.onmessage = (e) => {
    onStatus(true);
    onSnapshot(JSON.parse(e.data));
  };
  es.onerror = () => onStatus(false);
  return () => es.close();
}

export async function act<T = unknown>(action: string, body: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(`${BASE}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.error ?? `${action} failed`);
  return res.json();
}
