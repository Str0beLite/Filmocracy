// Pieces both screens use: icons, avatars, seats, posters, the QR code,
// confetti, the completion bar and a ticking clock.

function displayName(person, s) {
  return person.id === 'you' ? s.youName.trim() || 'You' : person.name;
}

function moodOf(person, s) {
  const id = person.id === 'you' ? s.youMood : person.mood;
  return D.moods.find((m) => m.id === id) || null;
}

function listNames(names) {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} & ${names[names.length - 1]}`;
}

function seatStatus(person, s) {
  if (s.seated.includes(person.id)) return 'seated';
  if (person.id === 'you' && s.phoneStep !== 'scan') return 'joining';
  return 'away';
}

function useNow(active, every = 200) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), every);
    return () => clearInterval(t);
  }, [active, every]);
  return now;
}

function trailerProgress(s, now) {
  if (s.phase !== 'trailer') return 1;
  return Math.min(1, Math.max(0, 1 - (s.trailerEndsAt - now) / TRAILER_MS));
}

function fmtTime(ms) {
  const sec = Math.round(ms / 1000);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}

const ICON_PATHS = {
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  cross: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  play: <path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none" />,
  star: (
    <path
      d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.2l-5.7 3.1 1.2-6.4L2.8 9.5l6.4-.8z"
      fill="currentColor"
      stroke="none"
    />
  ),
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9.5" rx="2.5" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  insta: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="5.5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.4" cy="6.6" r="1.1" fill="currentColor" stroke="none" />
    </>
  ),
  skip: <path d="M6 6l8 6-8 6zM17.5 6v12" />,
  restart: <path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4.5v4h4" />,
};

function Icon({ name, className = '' }) {
  return (
    <svg
      className={`icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

function Wordmark() {
  return (
    <span className="wordmark">
      <span className="wordmark-mark" aria-hidden="true" />
      tandem
    </span>
  );
}

function Avatar({ person, s, className = '' }) {
  return (
    <span className={`avatar ${className}`} style={{ '--who': person.color }} aria-hidden="true">
      {displayName(person, s).charAt(0).toUpperCase()}
    </span>
  );
}

function Badge({ kind }) {
  const icon = { yes: 'check', no: 'cross', locked: 'lock' }[kind];
  return (
    <span className={`badge badge--${kind}`}>
      {icon ? (
        <Icon name={icon} />
      ) : (
        <span className="dots">
          <i />
          <i />
          <i />
        </span>
      )}
    </span>
  );
}

// A theater seat with someone (or no one yet) in it. `children` float above it.
function Seat({ person, s, status = 'seated', badge, size = 'lg', showMood = false, children }) {
  const mood = moodOf(person, s);
  const caption = {
    seated: mood ? `${mood.emoji} ${mood.short}` : '',
    joining: 'Joining…',
    away: 'Not here yet',
  }[status];
  return (
    <div className={`seat seat--${size} is-${status} ${badge ? `has-${badge}` : ''}`}>
      {children}
      <div className="seat-back">
        <Avatar person={person} s={s} />
        {badge && <Badge kind={badge} key={badge} />}
      </div>
      <div className="seat-cushion" />
      <div className="seat-name">{displayName(person, s)}</div>
      {showMood && <div className="seat-mood">{caption}</div>}
    </div>
  );
}

// Loading bar for how close the night is to a movie.
function CompletionStatus({ value, className = '' }) {
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
        <b>{done ? 'Done' : `${value}%`}</b>
      </div>
      <div className="status-track">
        <i style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

// Where a pick came from. Never how anyone voted.
function PickStatus({ pick: p }) {
  if (!p.round) return <span className="pick-status is-predicted">Predicted for your group</span>;
  if (p.round.unanimous) {
    return (
      <span className="pick-status is-gold">
        <Icon name="star" /> Golden buzzer
      </span>
    );
  }
  return <span className="pick-status">From tonight's trailers</span>;
}

// Placeholder poster art built from the movie's palette.
function Poster({ movie, className = '' }) {
  const [c1, c2, c3] = movie.palette;
  return (
    <div
      className={`poster poster--${movie.motif} ${className}`}
      style={{ '--c1': c1, '--c2': c2, '--c3': c3 }}
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

// A real, scannable QR with rounded modules and branded finder eyes.
function QR({ text, className = '' }) {
  const { n, dots } = useMemo(() => {
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    const size = qr.getModuleCount();
    const inFinder = (r, c) => (r < 7 && c < 7) || (r < 7 && c >= size - 7) || (r >= size - 7 && c < 7);
    const cells = [];
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
          <rect className="qr-eye" x={c + 2} y={r + 2} width="3" height="3" rx="0.9" />
        </g>
      ))}
    </svg>
  );
}

const GOLDS = ['#ffd34d', '#f5b400', '#fff1b8', '#e0a000', '#ffe9a6', '#ffffff'];

function Confetti({ count = 70 }) {
  const pieces = useMemo(
    () =>
      Array.from({ length: count }, () => ({
        left: Math.random() * 100,
        delay: Math.random() * 3,
        dur: 3.2 + Math.random() * 2.8,
        rot: Math.floor(Math.random() * 360),
        sway: (Math.random() * 16 - 8).toFixed(1),
        color: pick(GOLDS),
        wide: Math.random() < 0.3,
      })),
    [count],
  );
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => (
        <i
          key={i}
          className={p.wide ? 'is-wide' : ''}
          style={{
            left: `${p.left}%`,
            background: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.dur}s`,
            '--rot': `${p.rot}deg`,
            '--sway': `${p.sway}em`,
          }}
        />
      ))}
    </div>
  );
}
