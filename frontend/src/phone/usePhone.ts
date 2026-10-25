import { createContext, useContext } from 'react';
import type { FeelingId } from '../api';

export interface PhoneState {
  me: string | null; // this phone's person id in the room
  setMe: (id: string | null) => void;
  feeling: FeelingId | null;
  setFeeling: (f: FeelingId) => void;
  shots: string[]; // object URLs of the chosen screenshots
  setShots: (urls: string[]) => void;
  myVotes: Record<number, 'yes' | 'no'>; // only this phone knows how it voted
  setMyVote: (round: number, vote: 'yes' | 'no') => void;
}

export const PhoneCtx = createContext<PhoneState | null>(null);

export function usePhone() {
  const s = useContext(PhoneCtx);
  if (!s) throw new Error('usePhone needs <PhoneStore>');
  return s;
}
