// This phone's identity and private choices. Kept in sessionStorage so a
// refresh keeps your seat, while each browser tab can be a different person
// (handy for testing on one laptop).

import { useState, type ReactNode } from 'react';
import type { FeelingId } from '../api';
import { PhoneCtx } from './usePhone';

function load<T>(key: string, fallback: T): T {
  try {
    const raw = sessionStorage.getItem(`tandem-${key}`);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: unknown) {
  try {
    sessionStorage.setItem(`tandem-${key}`, JSON.stringify(value));
  } catch {
    // storage blocked (private mode): the phone still works until a refresh
  }
}

export function PhoneStore({ children }: { children: ReactNode }) {
  const [me, setMeState] = useState<string | null>(() => load('me', null));
  const [feeling, setFeeling] = useState<FeelingId | null>(null);
  const [shots, setShots] = useState<string[]>([]);
  const [myVotes, setVotes] = useState<Record<number, 'yes' | 'no'>>(() => load('votes', {}));

  const setMe = (id: string | null) => {
    setMeState(id);
    save('me', id);
    if (!id) {
      setVotes({});
      save('votes', {});
    }
  };
  const setMyVote = (round: number, vote: 'yes' | 'no') => {
    const next = { ...myVotes, [round]: vote };
    setVotes(next);
    save('votes', next);
  };

  return (
    <PhoneCtx.Provider value={{ me, setMe, feeling, setFeeling, shots, setShots, myVotes, setMyVote }}>
      {children}
    </PhoneCtx.Provider>
  );
}
