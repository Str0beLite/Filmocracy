// Trailers from TMDB by tmdb_id: the movie's YouTube videos, best trailer first.
// Without VITE_TMDB_TOKEN (or if TMDB has nothing) screens keep the placeholder art.

import { useEffect, useState } from 'react';

const TOKEN = import.meta.env.VITE_TMDB_TOKEN as string | undefined;

type Video = { key: string; site: string; type: string; official: boolean };

const rank = (v: Video) => (v.type === 'Trailer' ? 0 : 2) + (v.official ? 0 : 1);

const cache = new Map<number, Promise<string | null>>();

export function trailerKey(tmdbId: number | null): Promise<string | null> {
  if (!TOKEN || !tmdbId) return Promise.resolve(null);
  if (!cache.has(tmdbId)) {
    cache.set(
      tmdbId,
      fetch(`https://api.themoviedb.org/3/movie/${tmdbId}/videos?language=en-US`, {
        headers: { Authorization: `Bearer ${TOKEN}` },
      })
        .then((r) => (r.ok ? r.json() : { results: [] }))
        .then(({ results }: { results: Video[] }) => {
          const best = results
            .filter((v) => v.site === 'YouTube' && (v.type === 'Trailer' || v.type === 'Teaser'))
            .sort((a, b) => rank(a) - rank(b))[0];
          return best?.key ?? null;
        })
        .catch(() => null),
    );
  }
  return cache.get(tmdbId)!;
}

export const youtubeUrl = (key: string) => `https://www.youtube.com/watch?v=${key}`;

// The YouTube key for a film, or null while loading / when there isn't one.
// `known` is a trailer the backend already checked is playable; it wins.
export function useTrailer(tmdbId: number | null, known: string | null = null) {
  const [found, setFound] = useState<{ id: number | null; key: string | null }>({ id: null, key: null });
  useEffect(() => {
    if (known) return;
    let live = true;
    trailerKey(tmdbId).then((key) => live && setFound({ id: tmdbId, key }));
    return () => {
      live = false;
    };
  }, [tmdbId, known]);
  return known ?? (found.id === tmdbId ? found.key : null);
}
