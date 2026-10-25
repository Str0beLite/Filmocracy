// The natural next screen for each route. The big screen uses it to move on
// by itself (when a trailer ends, after the verdict); the dev bar uses it
// to step through phone screens that are waiting on the big screen.

import { getRound } from '../api';
import { afterResult, isCheckpoint } from './night';

export async function nextPath(path: string): Promise<string> {
  const [, device, screen, arg] = path.split('/');
  const n = Number(arg) || 1;

  if (device === 'tv') {
    switch (screen) {
      case 'lobby':
        return '/tv/trailer/1';
      case 'trailer':
        return `/tv/vote/${n}`;
      case 'vote':
        return `/tv/reveal/${n}`;
      case 'reveal':
        return afterResult(n, (await getRound(n)).outcome);
      case 'miss':
      case 'checkpoint':
        return `/tv/trailer/${n + 1}`;
      case 'buzzer':
        return '/tv/picks';
      case 'picks':
        return '/tv/showing';
      default:
        return '/tv/lobby';
    }
  }

  switch (screen) {
    case 'join':
      return '/phone/sign-in';
    case 'sign-in':
      return '/phone/feeling';
    case 'feeling':
      return '/phone/screenshots';
    case 'screenshots':
      return '/phone/reading';
    case 'reading':
      return '/phone/lobby';
    case 'lobby':
      return '/phone/react/1';
    case 'react':
      return `/phone/vote/${n}`;
    case 'vote':
      return `/phone/voted/${n}`;
    case 'voted': {
      if ((await getRound(n)).outcome === 'buzzer') return `/phone/buzzer/${n}`;
      return isCheckpoint(n) ? `/phone/checkpoint/${n}` : `/phone/miss/${n}`;
    }
    case 'miss':
    case 'checkpoint':
      return `/phone/react/${n + 1}`;
    case 'buzzer':
      return '/phone/picks';
    case 'picks':
      return '/phone/showing';
    default:
      return '/phone/join';
  }
}
