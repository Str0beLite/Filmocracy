// Wraps every phone route: onboarding state, and a short rise between screens.

import { useRef } from 'react';
import { Outlet, useLocation } from 'react-router';
import { gsap, useMotion } from '../lib/motion';
import { DevBar } from '../dev/DevBar';
import { PhoneStore } from './store';

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
        <Outlet />
      </main>
      <DevBar />
    </PhoneStore>
  );
}
