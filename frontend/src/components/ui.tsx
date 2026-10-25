// Pieces both screens use: wordmark, avatars, seats, posters, QR, confetti,
// the completion bar and pick labels.

import { useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import qrcode from 'qrcode-generator';
import { Lock, Shuffle, Star } from 'lucide-react';
import { act, type Movie, type Person, type Pick } from '../api';
import { FEELING_ICONS, feelingOf } from '../lib/feelings';

// A button that sends one room action and stays disabled while it's in flight.
export function ActionButton({
  action,
  body,
  className,
  disabled,
  onDone,
  children,
}: {
  action: string;
  body?: Record<string, unknown>;
  className: string;
  disabled?: boolean;
  onDone?: () => void;
  children: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      className={className}
      disabled={disabled || busy}
      aria-busy={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await act(action, body);
          onDone?.();
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
    </button>
  );
}

export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`wordmark ${className}`}>
      <span className="wordmark-mark" aria-hidden="true" />
      tandem
    </span>
  );
}

export function Avatar({ person }: { person: Person }) {
  return (
    <span className="avatar" style={{ '--who': person.color } as CSSProperties} aria-hidden="true">
      {person.name.charAt(0).toUpperCase()}
    </span>
  );
}

export function LivePill({ children }: { children: ReactNode }) {
  return (
    <span className="room-pill">
      <span className="live-dot" aria-hidden="true" />
      {children}
    </span>
  );
}

type SeatState = 'seated' | 'joining' | 'locked' | 'thinking';

// A theater seat with someone (or nobody yet) in it. Seats show who is here
// and who has voted, never how anyone voted. `children` float above it.
export function Seat({
  person,
  state = 'seated',
  small = false,
  showFeeling = false,
  children,
}: {
  person: Person;
  state?: SeatState;
  small?: boolean;
  showFeeling?: boolean;
  children?: ReactNode;
}) {
  const feeling = feelingOf(person);
  const FeelingIcon = feeling ? FEELING_ICONS[feeling.id] : null;
  return (
    <div className={`seat ${small ? 'seat--sm' : ''} is-${state}`}>
      {children}
      <div className="seat-back">
        <Avatar person={person} />
        {state === 'locked' && (
          <span className="badge" aria-label="Voted">
            <Lock strokeWidth={2.8} />
          </span>
        )}
        {state === 'thinking' && (
          <span className="badge" aria-label="Still deciding">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
          </span>
        )}
      </div>
      <div className="seat-cushion" />
      <div className="seat-name">{person.name}</div>
      {showFeeling && (
        <div className="seat-feeling">
          {state === 'joining' ? (
            'Joining…'
          ) : FeelingIcon && feeling ? (
            <>
              <FeelingIcon aria-hidden="true" />
              {feeling.short}
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

export function CompletionStatus({ value, className = '' }: { value: number; className?: string }) {
  const done = value >= 100;
  return (
    <div
      className={`status ${done ? 'is-done' : ''} ${className}`}
      role="progressbar"
      aria-label="Completion status"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
    >
      <div className="status-head">
        <span>Completion status</span>
        <b>{done ? 'Ready' : `${value}%`}</b>
      </div>
      <div className="status-track">
        <i style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

// Placeholder poster art from the movie's palette, until TMDB posters land.
export function Poster({ movie, className = '' }: { movie: Movie; className?: string }) {
  const [c1, c2, c3] = movie.palette;
  return (
    <div
      className={`poster poster--${movie.motif} ${className}`}
      style={{ '--c1': c1, '--c2': c2, '--c3': c3 } as CSSProperties}
      aria-hidden="true"
    >
      <div className="poster-art" />
      <div className="poster-type">
        <span className="poster-title">{movie.title}</span>
        <span className="poster-year">{movie.year}</span>
      </div>
    </div>
  );
}

// The backend's exploration picks: not the obvious choice, on purpose.
export function Wildcard() {
  return (
    <span className="wildcard">
      <Shuffle aria-hidden="true" strokeWidth={2.4} />
      Wildcard
    </span>
  );
}

// Where a pick came from. Never how anyone voted.
export function PickSource({ source }: { source: Pick['source'] }) {
  if (source === 'buzzer') {
    return (
      <span className="pick-source is-buzzer">
        <Star aria-hidden="true" fill="currentColor" strokeWidth={0} /> Golden buzzer
      </span>
    );
  }
  if (source === 'trailers') return <span className="pick-source is-trailers">From tonight’s trailers</span>;
  return <span className="pick-source">Predicted for your group</span>;
}

// A real, scannable QR with rounded modules and branded finder eyes.
export function QR({ text, className = '' }: { text: string; className?: string }) {
  const { n, dots } = useMemo(() => {
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    const size = qr.getModuleCount();
    const inFinder = (r: number, c: number) => (r < 7 && c < 7) || (r < 7 && c >= size - 7) || (r >= size - 7 && c < 7);
    const cells: [number, number][] = [];
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) if (qr.isDark(r, c) && !inFinder(r, c)) cells.push([r, c]);
    }
    return { n: size, dots: cells };
  }, [text]);
  const finders = [
    [0, 0],
    [0, n - 7],
    [n - 7, 0],
  ];
  return (
    <svg className={`qr ${className}`} viewBox={`-2 -2 ${n + 4} ${n + 4}`} role="img" aria-label="QR code to join the room">
      {dots.map(([r, c]) => (
        <rect key={`${r}-${c}`} x={c + 0.07} y={r + 0.07} width="0.86" height="0.86" rx="0.3" fill="#111" />
      ))}
      {finders.map(([r, c]) => (
        <g key={`f${r}-${c}`}>
          <rect x={c + 0.5} y={r + 0.5} width="6" height="6" rx="1.8" fill="none" stroke="#111" strokeWidth="1" />
          <rect x={c + 2} y={r + 2} width="3" height="3" rx="0.9" fill="var(--accent)" />
        </g>
      ))}
    </svg>
  );
}

const GOLDS = ['#ffd34d', '#f5b400', '#fff1b8', '#e0a000', '#ffe9a6', '#ffffff'];

// Seeded so it renders the same every time (and stays pure for React).
function seeded(seed: number) {
  return () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
}

export function Confetti({ count = 70 }: { count?: number }) {
  const pieces = useMemo(() => {
    const rand = seeded(count * 7919);
    return Array.from({ length: count }, () => ({
      left: rand() * 100,
      delay: rand() * 3,
      dur: 3.2 + rand() * 2.8,
      rot: Math.floor(rand() * 360),
      sway: (rand() * 16 - 8).toFixed(1),
      color: GOLDS[Math.floor(rand() * GOLDS.length)],
      wide: rand() < 0.3,
    }));
  }, [count]);
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => (
        <i
          key={i}
          className={p.wide ? 'is-wide' : ''}
          style={
            {
              left: `${p.left}%`,
              background: p.color,
              animationDelay: `${p.delay}s`,
              animationDuration: `${p.dur}s`,
              '--rot': `${p.rot}deg`,
              '--sway': `${p.sway}em`,
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}
