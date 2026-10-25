// Display helpers both screens share.

import type { Snapshot } from '../api';

// Completion status is a loading bar, not a model score: seating everyone
// fills 30%, each trailer closes part of the remaining gap, picks hit 100%.
export function completion(s: Snapshot) {
  if (s.phase === 'picks' || s.phase === 'showing' || s.outcome === 'buzzer') return 100;
  const seated = s.people.filter((p) => p.seated).length;
  const setup = 30 * (s.people.length ? seated / s.people.length : 0);
  const rounds = s.phase === 'result' ? s.round : Math.max(0, s.round - 1);
  return Math.round(setup + (100 - setup) * (1 - Math.pow(0.6, rounds)) * 0.92);
}

export function listNames(names: string[]) {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} & ${names[names.length - 1]}`;
}

// How far into the current trailer, 0..1. Frozen while the TV has it paused.
export function trailerProgress(s: Snapshot, now: number) {
  const at = (s.pausedAt ?? now) - (s.trailerStartedAt ?? now);
  return Math.min(1, Math.max(0, at / s.trailerMs));
}

export function fmtTime(ms: number) {
  const sec = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}

// The URL in the TV's QR code. When the TV runs on localhost, phones need the
// laptop's Wi-Fi address instead (vite.config.ts works it out).
export function joinUrl(code: string) {
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  const origin = local && __LAN_ORIGIN__ ? __LAN_ORIGIN__ : location.origin;
  return `${origin}/phone/join?room=${code}`;
}
