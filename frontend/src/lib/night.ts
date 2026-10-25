// Rules of the night that both screens share.

import type { Outcome } from '../api';

export const CHECKPOINT_EVERY = 5;
export const TRAILER_MS = 12000;

export const isCheckpoint = (n: number) => n % CHECKPOINT_EVERY === 0;

// Where the big screen goes after a trailer's result.
export function afterResult(n: number, outcome: Outcome) {
  if (outcome === 'buzzer') return `/tv/buzzer/${n}`;
  return isCheckpoint(n) ? `/tv/checkpoint/${n}` : `/tv/miss/${n}`;
}

// Completion status is a loading bar, not a model score: seating everyone
// fills 30%, each trailer closes part of the remaining gap, picks hit 100%.
export function completion(round: number, seated = 1) {
  const setup = 30 * seated;
  if (round <= 0) return Math.round(setup);
  return Math.round(setup + (100 - setup) * (1 - Math.pow(0.6, round)) * 0.92);
}

export function listNames(names: string[]) {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} & ${names[names.length - 1]}`;
}

export function fmtTime(ms: number) {
  const sec = Math.round(ms / 1000);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}

// The URL in the TV's QR code. When the TV runs on localhost, phones need the
// laptop's Wi-Fi address instead (vite.config.ts works it out).
export function joinUrl(code: string) {
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  const origin = local && __LAN_ORIGIN__ ? __LAN_ORIGIN__ : location.origin;
  return `${origin}/phone/join?room=${code}`;
}
