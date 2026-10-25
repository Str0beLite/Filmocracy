// Keeps every screen in sync with the room. Until the first snapshot lands,
// shows a quiet "finding the room" state instead of half-empty screens.

import { useEffect, useState, type ReactNode } from 'react';
import { connect, type Snapshot } from '../api';
import { Wordmark } from '../components/ui';
import { RoomCtx } from './useRoom';

export function RoomProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<Snapshot | null>(null);
  const [online, setOnline] = useState(true);
  const [offset, setOffset] = useState(0);

  useEffect(
    () =>
      connect(
        (snap) => {
          setS(snap);
          setOffset(snap.serverNow - Date.now());
        },
        setOnline,
      ),
    [],
  );

  if (!s) {
    return (
      <div className="connecting" role="status">
        <Wordmark />
        <p>Finding the room…</p>
      </div>
    );
  }
  return (
    <RoomCtx.Provider value={{ s, online, offset }}>
      {children}
      {!online && (
        <p className="offline" role="status">
          Reconnecting…
        </p>
      )}
    </RoomCtx.Provider>
  );
}
