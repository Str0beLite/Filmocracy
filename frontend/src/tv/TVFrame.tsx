// The 16:9 big screen around every TV route, with curtains that part when the
// show starts and a cut from black between screens.

import { useRef } from 'react';
import { Outlet, useLocation } from 'react-router';
import { gsap, useMotion } from '../lib/motion';
import { DevBar } from '../dev/DevBar';

export function TVFrame() {
  const { pathname } = useLocation();
  const open = !pathname.startsWith('/tv/lobby');
  const screen = useRef<HTMLDivElement>(null);

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
        <Outlet />
        <div className={`curtains ${open ? 'is-open' : ''}`} aria-hidden="true">
          <div className="curtain curtain--left" />
          <div className="curtain curtain--right" />
          <div className="valance" />
        </div>
      </div>
      <DevBar />
    </main>
  );
}
