// Dev-only controls on the right edge. TV: fast-forward the night (ends the
// trailer, then closes voting as it stands). Phone: leave the room. Hidden in
// production builds.

import { Link } from 'react-router';
import { FastForward, LayoutGrid, LogOut } from 'lucide-react';
import { act } from '../api';
import { usePhone } from '../phone/usePhone';

function LeaveButton() {
  const { setMe } = usePhone();
  return (
    <button
      onClick={() => act('leave').finally(() => setMe(null))}
      aria-label="Leave the room on this phone"
      title="Leave the room"
    >
      <LogOut aria-hidden="true" />
    </button>
  );
}

export function DevBar({ device }: { device: 'tv' | 'phone' }) {
  if (!import.meta.env.DEV) return null;
  return (
    <nav className="devbar" aria-label="Dev controls">
      {device === 'tv' ? (
        <button onClick={() => act('devAdvance')} aria-label="Fast-forward" title="Fast-forward">
          <FastForward aria-hidden="true" />
        </button>
      ) : (
        <LeaveButton />
      )}
      <Link to="/" aria-label="All screens" title="All screens">
        <LayoutGrid aria-hidden="true" />
      </Link>
    </nav>
  );
}
