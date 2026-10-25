// What this phone picked during onboarding. In memory only: a refresh falls
// back to the mock, which is fine until the backend remembers it.

import { useState, type ReactNode } from 'react';
import type { FeelingId } from '../api';
import { PhoneCtx } from './usePhone';

export function PhoneStore({ children }: { children: ReactNode }) {
  const [feeling, setFeeling] = useState<FeelingId | null>(null);
  const [shots, setShots] = useState<string[]>([]);
  return <PhoneCtx.Provider value={{ feeling, setFeeling, shots, setShots }}>{children}</PhoneCtx.Provider>;
}
