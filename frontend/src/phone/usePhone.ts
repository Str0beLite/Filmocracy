import { createContext, useContext } from 'react';
import type { FeelingId } from '../api';

interface PhoneState {
  feeling: FeelingId | null;
  setFeeling: (f: FeelingId) => void;
  shots: string[]; // object URLs of the chosen screenshots
  setShots: (urls: string[]) => void;
}

export const PhoneCtx = createContext<PhoneState | null>(null);

export function usePhone() {
  const s = useContext(PhoneCtx);
  if (!s) throw new Error('usePhone needs <PhoneStore>');
  return s;
}
