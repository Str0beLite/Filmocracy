// GSAP for the big moments only. Content is visible by default; animations
// run `from` a hidden state and are skipped entirely for reduced motion.

import { useEffect, useState, type RefObject } from 'react';
import { useNavigate } from 'react-router';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

export { gsap };

export function useMotion(build: () => void, scope: RefObject<HTMLElement | null>, dependencies: unknown[] = []) {
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add('(prefers-reduced-motion: no-preference)', build);
      return () => mm.revert();
    },
    { scope, dependencies, revertOnUpdate: true },
  );
}

// Milliseconds since the screen mounted, ticking every `every` ms.
export function useElapsed(every = 200) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), every);
    return () => clearInterval(t);
  }, [every]);
  return now - start;
}

// Moves on to `to` after `ms`, the way the real night advances on its own.
export function useAutoAdvance(to: string | null, ms: number) {
  const navigate = useNavigate();
  useEffect(() => {
    if (!to) return;
    const t = setTimeout(() => navigate(to), ms);
    return () => clearTimeout(t);
  }, [to, ms, navigate]);
}
