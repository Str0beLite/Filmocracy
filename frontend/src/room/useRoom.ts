import { createContext, useContext, useEffect, useState } from 'react';
import type { Snapshot } from '../api';

export interface RoomState {
  s: Snapshot;
  online: boolean;
  offset: number; // server clock minus ours
}

export const RoomCtx = createContext<RoomState | null>(null);

export function useRoom() {
  const r = useContext(RoomCtx);
  if (!r) throw new Error('useRoom needs <RoomProvider>');
  return r;
}

// Server time now, re-rendering every `every` ms. Timers are the server's;
// screens only draw progress bars from it.
export function useServerNow(every = 200) {
  const { offset } = useRoom();
  const [now, setNow] = useState(() => Date.now() + offset);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() + offset), every);
    return () => clearInterval(t);
  }, [offset, every]);
  return now;
}
