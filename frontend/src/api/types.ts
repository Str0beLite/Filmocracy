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
  match: number; // 0–100, for display
  wildcard: boolean;
  why: { who: string; tag: string }[]; // whose feed pushed it up, and which tag
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
}

export interface Room {
  code: string;
  name: string;
  people: Person[];
}

export type Outcome = 'buzzer' | 'miss';

export interface Round {
  n: number; // 1-based trailer number tonight
  movie: Movie;
  outcome: Outcome;
}

export interface Pick {
  movie: Movie;
  source: 'buzzer' | 'trailers' | 'predicted';
}

export interface Picks {
  top: Pick[];
  more: Movie[];
}

export interface Emote {
  emoji: string;
  label: string;
}
