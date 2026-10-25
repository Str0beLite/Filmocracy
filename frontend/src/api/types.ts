// `Rec` matches the backend's rec shape (backend/README.md, "API").
// Everything else is what the screens need; when the backend is wired in,
// `src/api/index.ts` builds these from real responses instead of mock.ts.

export interface Rec {
  rec_id: number | null;
  id: number; // MovieLens id
  title: string;
  year: number;
  tmdb_id: number | null;
  tags: string[];
  score: number;
  because_of: string[];
  explore?: boolean; // one of the backend's exploration picks (ranks 11–50)
}

// What TMDB will fill in later. Art is placeholder poster/trailer styling.
export interface MovieDetails {
  runtime: string;
  genres: string[];
  logline: string;
  palette: [string, string, string];
  motif: 'rays' | 'eye' | 'halftone' | 'horizon';
}

export interface Movie extends MovieDetails {
  id: number;
  tmdbId: number | null;
  title: string;
  year: number;
  tags: string[];
  match: number; // 0–100, for display
  wildcard: boolean;
}

export type FeelingId = 'laugh' | 'edge' | 'feels' | 'mindblown' | 'cozy' | 'hyped';

export interface Feeling {
  id: FeelingId;
  label: string;
  short: string;
  boost: string[]; // catalog tags sent as the backend's mood boost
}

export interface Person {
  id: string;
  name: string;
  color: string;
  feeling: FeelingId | null;
  seated: boolean; // false while they're still onboarding on their phone
}

export type Phase = 'lobby' | 'trailer' | 'vote' | 'reveal' | 'result' | 'picks' | 'showing';

export type Outcome = 'buzzer' | 'miss' | 'checkpoint';

export interface PickSource {
  id: number;
  source: 'buzzer' | 'trailers' | 'predicted';
}

export interface Reaction {
  id: number;
  who: string;
  emoji: string;
  at: number;
}

// What every screen sees. It never says how anyone voted: only who has
// (`locked`) and whether it was unanimous (`outcome`).
export interface Snapshot {
  serverNow: number;
  code: string;
  name: string;
  people: Person[];
  phase: Phase;
  round: number; // 1-based trailer number tonight; 0 in the lobby
  movieId: number | null;
  why: { who: string; tag: string }[]; // whose feed pushed the current trailer up
  trailerStartedAt: number | null;
  trailerMs: number; // this trailer's length: the real video's once it plays, else TRAILER_MS
  locked: string[];
  outcome: Outcome | null;
  shown: number[]; // movie ids, in the order they played
  picks: { top: PickSource[]; more: number[] } | null;
  showingId: number | null;
  reactions: Reaction[];
}

export interface Pick {
  movie: Movie;
  source: PickSource['source'];
}

export interface Emote {
  emoji: string;
  label: string;
}
