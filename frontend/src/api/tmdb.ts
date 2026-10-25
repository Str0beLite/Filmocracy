// Trailers and posters from TMDB by tmdb_id, for films the backend has no stored details for.
// One call per film gets both. Without VITE_TMDB_TOKEN (or if TMDB has nothing) screens keep the placeholder art.

import { useEffect, useState } from 'react';

const TOKEN = import.meta.env.VITE_TMDB_TOKEN as string | undefined;

type Video = { key: string; site: string; type: string; official: boolean };
type Found = { trailer: string | null; poster: string | null };

const rank = (v: Video) => (v.type === 'Trailer' ? 0 : 2) + (v.official ? 0 : 1);

const cache = new Map<number, Promise<Found>>();

function lookup(tmdbId: number | null): Promise<Found> {
  if (!TOKEN || !tmdbId) return Promise.resolve({ trailer: null, poster: null });
  if (!cache.has(tmdbId)) {
    cache.set(
      tmdbId,
      fetch(`https://api.themoviedb.org/3/movie/${tmdbId}?append_to_response=videos&language=en-US`, {
        headers: { Authorization: `Bearer ${TOKEN}` },
      })
        .then((r) => (r.ok ? r.json() : {}))
        .then((d: { poster_path?: string | null; videos?: { results: Video[] } }) => {
          const best = (d.videos?.results ?? [])
            .filter((v) => v.site === 'YouTube' && (v.type === 'Trailer' || v.type === 'Teaser'))
            .sort((a, b) => rank(a) - rank(b))[0];
          return {
            trailer: best?.key ?? null,
            poster: d.poster_path ? `https://image.tmdb.org/t/p/w500${d.poster_path}` : null,
          };
        })
        .catch(() => ({ trailer: null, poster: null })),
    );
  }
  return cache.get(tmdbId)!;
}

export const youtubeUrl = (key: string) => `https://www.youtube.com/watch?v=${key}`;

// A film's TMDB trailer key or poster URL, or null while loading / when there isn't one.
// `known` is what the backend already stored; it wins and skips the lookup.
function useTmdb(field: keyof Found, tmdbId: number | null, known: string | null) {
  const [found, setFound] = useState<{ id: number | null; value: string | null }>({ id: null, value: null });
  useEffect(() => {
    if (known) return;
    let live = true;
    lookup(tmdbId).then((f) => live && setFound({ id: tmdbId, value: f[field] }));
    return () => {
      live = false;
    };
  }, [field, tmdbId, known]);
  return known ?? (found.id === tmdbId ? found.value : null);
}

export const useTrailer = (tmdbId: number | null, known: string | null = null) => useTmdb('trailer', tmdbId, known);
export const usePoster = (tmdbId: number | null, known: string | null = null) => useTmdb('poster', tmdbId, known);
