// The 16:9 big screen around every TV route. It follows the room: whenever
// the night moves on, it navigates to the matching screen. The night opens
// behind full curtains that sway and draw back to reveal the lobby's QR code;
// the side drapes part when the show starts; every screen change cuts in from black.

import { useEffect, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { gsap, useMotion } from '../lib/motion';
import { tvPath } from '../lib/flow';
import { useRoom } from '../room/useRoom';
import { DevBar } from '../dev/DevBar';
import { act } from '../api';

export function TVFrame() {
  const { s } = useRoom();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const want = tvPath(s);
  const open = s.phase !== 'lobby';
  const screen = useRef<HTMLDivElement>(null);
  const reveal = s.phase === 'lobby';

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

  useMotion(
    () => {
      if (!reveal) return;
      gsap
        .timeline({ defaults: { duration: 1.7, ease: 'power3.inOut' } })
        .set('.reveal', { autoAlpha: 1 })
        .to('.reveal-panel--left', { xPercent: 2, duration: 0.22, ease: 'sine.inOut', yoyo: true, repeat: 1 }, 0.4)
        .to('.reveal-panel--right', { xPercent: -2, duration: 0.22, ease: 'sine.inOut', yoyo: true, repeat: 1 }, 0.4)
        .to('.reveal-panel--left', { xPercent: -100, scaleX: 0.55 }, 0.95)
        .to('.reveal-panel--right', { xPercent: 100, scaleX: 0.55 }, 0.95)
        .set('.reveal', { autoAlpha: 0 });
    },
    screen,
    [reveal],
  );

  return (
    <main className="tv">
      <div className="tv-screen" ref={screen}>
        {pathname === want && <Outlet />}
        {s.joined && (
          <button
            className="tv-btn tv-btn--ghost tv-btn--sm tv-end"
            onClick={() => confirm('End this session for everyone and go back to the start?') && act('end')}
          >
            End session
          </button>
        )}
        <div className={`curtains ${open ? 'is-open' : ''}`} aria-hidden="true">
          <div className="curtain curtain--left" />
          <div className="curtain curtain--right" />
          <div className="valance" />
        </div>
        <div className="reveal" aria-hidden="true">
          <div className="reveal-panel reveal-panel--left" />
          <div className="reveal-panel reveal-panel--right" />
        </div>
      </div>
      <DevBar device="tv" />
    </main>
  );
}
