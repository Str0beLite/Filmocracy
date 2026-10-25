// Which screen each device should show for the room's current state. The
// frames navigate there whenever the room changes, so every device moves
// together and the URL always names the screen.

import type { Snapshot } from '../api';

function resultPath(device: 'tv' | 'phone', s: Snapshot) {
  return `/${device}/${s.outcome ?? 'miss'}/${s.round}`;
}

export function tvPath(s: Snapshot): string {
  switch (s.phase) {
    case 'lobby':
      return '/tv/lobby';
    case 'trailer':
    case 'vote':
    case 'reveal':
      return `/tv/${s.phase === 'trailer' ? 'trailer' : s.phase}/${s.round}`;
    case 'result':
      return resultPath('tv', s);
    case 'picks':
      return '/tv/picks';
    case 'showing':
      return `/tv/showing/${s.showingId ?? ''}`;
  }
}

// Only for a phone that has taken its seat; before that it's onboarding.
export function phonePath(s: Snapshot, me: string): string {
  switch (s.phase) {
    case 'lobby':
      return '/phone/lobby';
    case 'trailer':
      return `/phone/${s.locked.includes(me) ? 'voted' : 'react'}/${s.round}`;
    case 'vote':
      return `/phone/${s.locked.includes(me) ? 'voted' : 'vote'}/${s.round}`;
    case 'reveal':
      return `/phone/voted/${s.round}`;
    case 'result':
      return resultPath('phone', s);
    case 'picks':
      return '/phone/picks';
    case 'showing':
      return `/phone/showing/${s.showingId ?? ''}`;
  }
}

export const ONBOARDING = ['/phone/join', '/phone/name', '/phone/feeling', '/phone/screenshots', '/phone/reading'];
