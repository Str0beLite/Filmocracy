// The phone: scan in, connect Instagram, see your vibe, react, vote.

function phoneScreen({ s, unanimous }) {
  if (s.phoneStep !== 'seated') return s.phoneStep;
  switch (s.phase) {
    case 'lobby':
      return 'lobby';
    case 'trailer':
      return 'react';
    case 'voting':
      return s.votes.you ? 'waiting' : 'vote';
    case 'reveal':
      return 'waiting';
    case 'result':
      return unanimous ? 'buzzer' : 'miss';
    default:
      return 'showing';
  }
}

function Phone({ night }) {
  const screen = phoneScreen(night);
  const Screen = PHONE_SCREENS[screen];
  const darkTop = ['scan', 'buzzer', 'showing'].includes(screen);
  const darkBottom = ['buzzer', 'showing'].includes(screen);
  return (
    <div className="phone">
      <div className={`phone-screen ${darkTop ? 'dark-top' : ''} ${darkBottom ? 'dark-bottom' : ''}`}>
        <div className="phone-island" />
        <StatusBar />
        <div className="phone-body">
          <Screen key={`${screen}-${night.s.movieIdx}`} night={night} />
        </div>
        <div className="home-bar" />
      </div>
    </div>
  );
}

function StatusBar() {
  return (
    <div className="statusbar">
      <span>9:41</span>
      <span className="statusbar-icons" aria-hidden="true">
        <svg viewBox="0 0 18 12">
          <rect x="0" y="8" width="3" height="4" rx="1" />
          <rect x="5" y="5.5" width="3" height="6.5" rx="1" />
          <rect x="10" y="3" width="3" height="9" rx="1" />
          <rect x="15" y="0" width="3" height="12" rx="1" />
        </svg>
        <svg viewBox="0 0 16 12">
          <path d="M8 2.2c2.4 0 4.6.9 6.3 2.5l1.2-1.3A10.6 10.6 0 0 0 8 .4 10.6 10.6 0 0 0 .5 3.4l1.2 1.3A8.8 8.8 0 0 1 8 2.2zm0 3.5c1.4 0 2.7.5 3.8 1.4L13 5.8a7.3 7.3 0 0 0-10 0l1.2 1.3A5.6 5.6 0 0 1 8 5.7zm0 3.4c.6 0 1.2.2 1.6.6L8 11.6 6.4 9.7c.4-.4 1-.6 1.6-.6z" />
        </svg>
        <svg viewBox="0 0 27 13">
          <rect x=".5" y=".5" width="23" height="12" rx="3.5" fill="none" stroke="currentColor" opacity=".45" />
          <rect x="2" y="2" width="18" height="9" rx="2" />
          <path d="M25 4.5v4c.8-.3 1.5-1.1 1.5-2s-.7-1.7-1.5-2z" opacity=".45" />
        </svg>
      </span>
    </div>
  );
}

function RoomPill() {
  return (
    <span className="room-pill">
      <span className="live-dot" />
      Room {D.room.code} · {D.room.name}
    </span>
  );
}

function PhoneScan({ night }) {
  const scan = () => night.dispatch({ type: 'scan' });
  return (
    <section className="ps ps--scan">
      <button className="viewfinder" onClick={scan} aria-label="Scan the QR code (demo)">
        <span className="vf-room" />
        <span className="vf-tv">
          <QR text={`https://tandem.example/j/${D.room.code}`} className="qr--mini" />
        </span>
        <span className="vf-frame">
          <i />
          <i />
          <i />
          <i />
          <span className="vf-line" />
        </span>
      </button>
      <div className="scan-sheet">
        <p className="eyebrow">Movie night?</p>
        <h1 className="ps-title">Scan the code on the big screen</h1>
        <button className="btn btn-primary" onClick={scan}>
          Scan (demo)
        </button>
        <button className="btn btn-ghost" onClick={scan}>
          Enter room code
        </button>
      </div>
    </section>
  );
}

function PhoneConnect({ night }) {
  const { s, dispatch } = night;
  return (
    <section className="ps ps--connect">
      <RoomPill />
      <h1 className="ps-title">Grab a seat</h1>
      <p className="ps-sub">Connect Instagram and Tandem works out what you'll actually want to watch. No quizzes.</p>
      <label className="field">
        <span>Your name</span>
        <input
          value={s.youName}
          maxLength={16}
          placeholder="What do friends call you?"
          onChange={(e) => dispatch({ type: 'setName', name: e.target.value })}
        />
      </label>
      <div className="reads">
        <p className="eyebrow">What we look at</p>
        <ul>
          <li><Icon name="check" />Reels you like, save and finish</li>
          <li><Icon name="check" />Posts you save</li>
          <li><Icon name="check" />Accounts you follow</li>
        </ul>
      </div>
      <div className="ps-foot">
        <button className="btn btn-insta" onClick={() => dispatch({ type: 'phoneStep', step: 'analyzing' })}>
          <Icon name="insta" /> Continue with Instagram
        </button>
        <p className="fineprint">Read-only. Tandem never posts or messages for you.</p>
      </div>
    </section>
  );
}

function PhoneAnalyzing({ night }) {
  const you = D.people.find((p) => p.id === 'you');
  return (
    <section className="ps ps--analyzing">
      <div className="orb">
        <Avatar person={you} s={night.s} />
      </div>
      <h1 className="ps-title">Reading your vibe…</h1>
      <ul className="signals">
        {D.you.signals.map((text, i) => (
          <li key={text} style={{ animationDelay: `${0.3 + i * 0.75}s` }}>
            <Icon name="check" />
            {text}
          </li>
        ))}
      </ul>
    </section>
  );
}

function PhoneVibe({ night }) {
  const { dispatch } = night;
  const vibe = D.you.vibe;
  const takeSeat = () => {
    dispatch({ type: 'seat', id: 'you' });
    dispatch({ type: 'phoneStep', step: 'seated' });
  };
  return (
    <section className="ps ps--vibe">
      <p className="eyebrow">Your movie vibe</p>
      <div className="vibe-card">
        <h1 className="vibe-title">{vibe.title}</h1>
        <p>{vibe.blurb}</p>
        <div className="traits">
          {vibe.traits.map(([label, value], i) => (
            <div className="trait" key={label}>
              <span>{label}</span>
              <span className="bar">
                <i style={{ width: `${value}%`, animationDelay: `${0.15 + i * 0.12}s` }} />
              </span>
              <b>{value}</b>
            </div>
          ))}
        </div>
        <div className="tags">
          {vibe.tags.map((t) => (
            <span className="tag" key={t}>
              {t}
            </span>
          ))}
        </div>
      </div>
      <div className="ps-foot">
        <button className="btn btn-primary" onClick={takeSeat}>
          Take my seat <Icon name="arrow" />
        </button>
      </div>
    </section>
  );
}

function PhoneLobby({ night }) {
  const { s, everyoneSeated, start } = night;
  const missing = D.people.filter((p) => !s.seated.includes(p.id));
  return (
    <section className="ps ps--lobby">
      <RoomPill />
      <h1 className="ps-title">You're in.</h1>
      <p className="ps-sub">Trailers play on the big screen. You react and vote from here.</p>
      <ul className="crew">
        {D.people.map((p) => {
          const here = s.seated.includes(p.id);
          return (
            <li key={p.id} className={here ? '' : 'is-away'}>
              <Avatar person={p} s={s} />
              <span className="crew-who">
                <b>
                  {displayName(p, s)}
                  {p.id === 'you' && ' (you)'}
                </b>
                <span>{here ? p.vibe : 'Not here yet'}</span>
              </span>
              {here ? <Icon name="check" className="crew-status" /> : <Badge kind="thinking" />}
            </li>
          );
        })}
      </ul>
      <div className="ps-foot">
        <button className="btn btn-primary" disabled={!everyoneSeated} onClick={start}>
          {everyoneSeated ? 'Start the show' : `Waiting for ${missing.map((p) => p.name).join(' & ')}…`}
        </button>
      </div>
    </section>
  );
}

function NowPlaying({ movie, progress }) {
  return (
    <div className="now-playing">
      <Poster movie={movie} className="poster--thumb" />
      <div className="np-text">
        <p className="eyebrow">
          <span className="live-dot" /> On the big screen
        </p>
        <p className="np-title">{movie.title}</p>
        <div className="np-progress">
          <i style={{ width: `${progress * 100}%` }} />
        </div>
      </div>
    </div>
  );
}

function PhoneReact({ night }) {
  const { s, movie, react, dispatch } = night;
  const now = useNow(s.phase === 'trailer');
  const [bursts, setBursts] = useState([]);
  const send = (emote, idx) => {
    react('you', emote.emoji);
    setBursts((b) => [...b.slice(-8), { id: Date.now() + Math.random(), idx, emoji: emote.emoji }]);
  };
  return (
    <section className="ps ps--react">
      <NowPlaying movie={movie} progress={trailerProgress(s, now)} />
      <p className="eyebrow ps-label">React on the big screen</p>
      <div className="emote-grid">
        {D.emotes.map((e, i) => (
          <button key={e.emoji} className="emote" onClick={() => send(e, i)} aria-label={`React: ${e.label}`}>
            <span className="emote-emoji" aria-hidden="true">
              {e.emoji}
            </span>
            <small>{e.label}</small>
            {bursts
              .filter((b) => b.idx === i)
              .map((b) => (
                <span key={b.id} className="burst" aria-hidden="true">
                  {b.emoji}
                </span>
              ))}
          </button>
        ))}
      </div>
      <div className="ps-foot">
        <p className="fineprint">Voting opens when the trailer ends.</p>
        <button className="btn btn-ghost" onClick={() => dispatch({ type: 'endTrailer' })}>
          Skip to the vote
        </button>
      </div>
    </section>
  );
}

function PhoneVote({ night }) {
  const { movie, vote } = night;
  return (
    <section className="ps ps--vote">
      <div className="vote-head">
        <Poster movie={movie} className="poster--thumb" />
        <div>
          <p className="eyebrow">Just watched</p>
          <h2>{movie.title}</h2>
          <p className="vote-meta">
            {movie.year} · {movie.runtime}
          </p>
        </div>
      </div>
      <h1 className="ps-title vote-q">Watch it tonight?</h1>
      <div className="vote-buttons">
        <button className="vote-btn vote-btn--yes" onClick={() => vote('yes')}>
          <Icon name="check" />
          <span>I'm in</span>
        </button>
        <button className="vote-btn vote-btn--no" onClick={() => vote('no')}>
          <Icon name="cross" />
          <span>Pass</span>
        </button>
      </div>
      <p className="fineprint">Everyone has to say yes for the golden buzzer.</p>
    </section>
  );
}

function PhoneWaiting({ night }) {
  const { s, voteCount } = night;
  const mine = s.votes.you;
  const left = D.people.length - voteCount;
  const status =
    s.phase === 'reveal' ? 'Revealing on the big screen…' : left > 0 ? `Waiting on ${left} more…` : 'Everyone is locked in.';
  return (
    <section className="ps ps--waiting">
      <div className={`my-vote my-vote--${mine}`}>
        <Icon name={mine === 'yes' ? 'check' : 'cross'} />
      </div>
      <h1 className="ps-title">{mine === 'yes' ? "You're in." : 'You passed.'}</h1>
      <p className="ps-sub">{status}</p>
      <div className="lock-row">
        {D.people.map((p) => (
          <span key={p.id} className={`slot ${s.votes[p.id] ? 'is-locked' : ''}`}>
            <Avatar person={p} s={s} />
            {s.votes[p.id] && <Icon name="lock" />}
          </span>
        ))}
      </div>
    </section>
  );
}

function PhoneMiss({ night }) {
  const { s, movie, yesCount, revealOrder } = night;
  const byId = Object.fromEntries(D.people.map((p) => [p.id, p]));
  return (
    <section className="ps ps--miss">
      <p className="eyebrow">{movie.title}</p>
      <h1 className="ps-title">Not this one.</h1>
      <p className="ps-sub">
        {yesCount} of {D.people.length} said yes. No golden buzzer, no hard feelings.
      </p>
      <div className="tally">
        {revealOrder.map((id) => (
          <span key={id} className={`tally-seat is-${s.votes[id]}`}>
            <Avatar person={byId[id]} s={s} />
            <Icon name={s.votes[id] === 'yes' ? 'check' : 'cross'} />
          </span>
        ))}
      </div>
      <div className="ps-foot">
        <div className="countdown" style={{ animationDuration: `${MISS_PAUSE_MS}ms` }} />
        <p className="fineprint">Next trailer coming up…</p>
      </div>
    </section>
  );
}

function PhoneBuzzer({ night }) {
  const { movie, dispatch, nextTrailer } = night;
  return (
    <section className="ps ps--buzzer">
      <Confetti count={40} />
      <div className="buzzer-btn">
        <Icon name="star" />
      </div>
      <p className="eyebrow">
        {D.people.length} of {D.people.length} said yes
      </p>
      <h1 className="buzzer-title gold-text">Golden Buzzer</h1>
      <p className="buzzer-note">
        It's <b>{movie.title}</b> tonight. Grab the popcorn.
      </p>
      <div className="ps-foot">
        <button className="btn btn-gold" onClick={() => dispatch({ type: 'showMovie' })}>
          <Icon name="play" /> Start the movie
        </button>
        <button className="btn btn-ghost" onClick={nextTrailer}>
          Keep browsing
        </button>
      </div>
    </section>
  );
}

function PhoneShowing({ night }) {
  return (
    <section className="ps ps--showing">
      <div className="showing-icon" aria-hidden="true">
        🍿
      </div>
      <h1 className="ps-title">Phone down, eyes up.</h1>
      <p className="ps-sub">Enjoy {night.movie.title}. Your group's taste gets sharper every movie night.</p>
    </section>
  );
}

const PHONE_SCREENS = {
  scan: PhoneScan,
  connect: PhoneConnect,
  analyzing: PhoneAnalyzing,
  vibe: PhoneVibe,
  lobby: PhoneLobby,
  react: PhoneReact,
  vote: PhoneVote,
  waiting: PhoneWaiting,
  miss: PhoneMiss,
  buzzer: PhoneBuzzer,
  showing: PhoneShowing,
};
