// The 16:9 big screen around every TV route. It follows the room: whenever
// the night moves on, it navigates to the matching screen. Curtains part when
// the show starts; every screen change cuts in from black.

import { useEffect, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { gsap, useMotion } from '../lib/motion';
import { tvPath } from '../lib/flow';
import { useRoom } from '../room/useRoom';
import { DevBar } from '../dev/DevBar';

export function TVFrame() {
  const { s } = useRoom();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const want = tvPath(s);
  const open = s.phase !== 'lobby';
  const screen = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (pathname !== want) navigate(want, { replace: true });
  }, [pathname, want, navigate]);

  useMotion(
    () => {
      gsap.from('.tv-view', { autoAlpha: 0, duration: 0.6, ease: 'power2.out' });
    },
    screen,
    [pathname],
  );

  return (
    <main className="tv">
      <div className="tv-screen" ref={screen}>
        {pathname === want && <Outlet />}
        <div className={`curtains ${open ? 'is-open' : ''}`} aria-hidden="true">
          <div className="curtain curtain--left" />
          <div className="curtain curtain--right" />
          <div className="valance" />
        </div>
      </div>
      <DevBar device="tv" />
    </main>
  );
}
