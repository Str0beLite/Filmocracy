// Keeps every screen in sync with the room. Until the first snapshot lands,
// shows a quiet "finding the room" state instead of half-empty screens. The
// big screen hosts with its own device key, so it opens straight on the theater.

import { useEffect, useState, type ReactNode } from 'react';
import { connect, type Snapshot } from '../api';
import { Wordmark } from '../components/ui';
import { RoomCtx } from './useRoom';

function Room({ children }: { children: ReactNode }) {
  const [s, setS] = useState<Snapshot | null>(null);
  const [online, setOnline] = useState(true);
  const [offset, setOffset] = useState(0);

  useEffect(
    () =>
      connect(
        (snap) => {
          setS(snap);
          if (snap.serverNow) setOffset(snap.serverNow - Date.now());
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

export function RoomProvider({ children }: { children: ReactNode }) {
  // The dev home page isn't a device; it doesn't join or host anything.
  if (location.pathname === '/' || location.pathname.startsWith('/training')) return children;
  return <Room>{children}</Room>;
}
