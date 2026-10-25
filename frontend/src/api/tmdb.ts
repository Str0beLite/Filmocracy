// Trailers, posters, runtime, genres and summaries from TMDB by tmdb_id, for films the backend has no stored details
// for. One call per film gets them all. Without VITE_TMDB_TOKEN (or if TMDB has nothing) screens keep the placeholder art.

import { useEffect, useState } from 'react';

const TOKEN = import.meta.env.VITE_TMDB_TOKEN as string | undefined;

type Video = { key: string; site: string; type: string; official: boolean };
export type Found = { title: string; trailer: string | null; poster: string | null; runtime: string; genres: string[]; logline: string };
const NONE: Found = { title: '', trailer: null, poster: null, runtime: '', genres: [], logline: '' };

export const formatRuntime = (min?: number | null) =>
  min ? `${Math.floor(min / 60)}h ${min % 60}m`.replace(' 0m', '').replace(/^0h /, '') : '';

const rank = (v: Video) => (v.type === 'Trailer' ? 0 : 2) + (v.official ? 0 : 1);

const cache = new Map<number, Promise<Found>>();

export function tmdbDetails(tmdbId: number | null): Promise<Found> {
  if (!TOKEN || !tmdbId) return Promise.resolve(NONE);
  if (!cache.has(tmdbId)) {
    cache.set(
      tmdbId,
      fetch(`https://api.themoviedb.org/3/movie/${tmdbId}?append_to_response=videos&language=en-US`, {
        headers: { Authorization: `Bearer ${TOKEN}` },
      })
        .then((r) => (r.ok ? r.json() : {}))
        .then((d: {
          title?: string;
          poster_path?: string | null;
          runtime?: number | null;
          genres?: { name: string }[];
          overview?: string;
          videos?: { results: Video[] };
        }) => {
          const best = (d.videos?.results ?? [])
            .filter((v) => v.site === 'YouTube' && (v.type === 'Trailer' || v.type === 'Teaser'))
            .sort((a, b) => rank(a) - rank(b))[0];
          return {
            title: d.title ?? '',
            trailer: best?.key ?? null,
            poster: d.poster_path ? `https://image.tmdb.org/t/p/w500${d.poster_path}` : null,
            runtime: formatRuntime(d.runtime),
            genres: (d.genres ?? []).map((g) => g.name),
            logline: d.overview ?? '',
          };
        })
        .catch(() => NONE),
    );
  }
  return cache.get(tmdbId)!;
}

export const youtubeUrl = (key: string) => `https://www.youtube.com/watch?v=${key}`;

// A film's TMDB trailer key, or null while loading / when there isn't one.
// `known` is a trailer the backend already stored; it wins and skips the lookup.
export function useTrailer(tmdbId: number | null, known: string | null = null) {
  const [found, setFound] = useState<{ id: number | null; key: string | null }>({ id: null, key: null });
  useEffect(() => {
    if (known) return;
    let live = true;
    tmdbDetails(tmdbId).then((f) => live && setFound({ id: tmdbId, key: f.trailer }));
    return () => {
      live = false;
    };
  }, [tmdbId, known]);
  return known ?? (found.id === tmdbId ? found.key : null);
}
