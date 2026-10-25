// Wraps every phone route. Before you've taken your seat the phone walks
// through onboarding on its own; after that it follows the room, so it moves
// whenever the big screen does.

import { useEffect, useRef, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { gsap, useMotion } from '../lib/motion';
import { ONBOARDING, phonePath } from '../lib/flow';
import { useRoom } from '../room/useRoom';
import { DevBar } from '../dev/DevBar';
import { PhoneStore } from './store';
import { usePhone } from './usePhone';

function Follow({ children }: { children: ReactNode }) {
  const { s } = useRoom();
  const { me, setMe } = usePhone();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const person = s.people.find((p) => p.id === me);
  // Before you have a name, only the first three steps are open.
  const allowed = person ? ONBOARDING : ONBOARDING.slice(0, 3);
  const want = person?.seated ? phonePath(s, person.id) : allowed.includes(pathname) ? pathname : '/phone/join';

  // The room was reset (or the server restarted): start this phone over.
  useEffect(() => {
    if (me && !person) setMe(null);
  }, [me, person, setMe]);

  useEffect(() => {
    if (pathname !== want) navigate(want, { replace: true });
  }, [pathname, want, navigate]);

  return pathname === want ? children : null;
}

export function PhoneFrame() {
  const { pathname } = useLocation();
  const scope = useRef<HTMLElement>(null);
  useMotion(
    () => {
      gsap.from('.ps > *', { y: 14, autoAlpha: 0, stagger: 0.04, duration: 0.5, ease: 'expo.out' });
    },
    scope,
    [pathname],
  );
  return (
    <PhoneStore>
      <main className="phone" ref={scope}>
        <Follow>
          <Outlet />
        </Follow>
      </main>
      <DevBar device="phone" />
    </PhoneStore>
  );
}
