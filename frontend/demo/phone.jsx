// The phone: scan in, pick tonight's feeling, connect Instagram, react, vote.
// Once seated, a phone never moves the night forward; the big screen does.

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
    case 'picks':
      return 'picks';
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

// Shown wherever a phone is waiting on the big screen.
function WaitingNote({ children }) {
  return (
    <p className="waiting-note">
      <Badge kind="thinking" />
      {children}
    </p>
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

function PhoneMood({ night }) {
  const { s, dispatch } = night;
  return (
    <section className="ps ps--mood">
      <RoomPill />
      <h1 className="ps-title">How do you want to feel tonight?</h1>
      <p className="ps-sub">Filmocracy blends everyone's answer with what you all like on Instagram.</p>
      <div className="mood-grid" role="radiogroup" aria-label="Tonight's feeling">
        {D.moods.map((m) => (
          <button
            key={m.id}
            role="radio"
            aria-checked={s.youMood === m.id}
            className="mood"
            onClick={() => dispatch({ type: 'setMood', mood: m.id })}
          >
            <span className="mood-emoji" aria-hidden="true">
              {m.emoji}
            </span>
            {m.label}
          </button>
        ))}
      </div>
      <div className="ps-foot">
        <button
          className="btn btn-primary"
          disabled={!s.youMood}
          onClick={() => dispatch({ type: 'phoneStep', step: 'connect' })}
        >
          Continue <Icon name="arrow" />
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
      <p className="ps-sub">Connect Instagram and Filmocracy works out what you'll actually want to watch. No quizzes.</p>
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
        <p className="fineprint">Read-only. Filmocracy never posts or messages for you.</p>
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
      <h1 className="ps-title">Reading your feed…</h1>
      <ul className="signals">
        {D.you.signals.map((text, i) => (
          <li key={text} style={{ animationDelay: `${0.3 + i * 0.7}s` }}>
            <Icon name="check" />
            {text}
          </li>
        ))}
      </ul>
    </section>
  );
}

const HOW_IT_WORKS = [
  { icon: '🎬', text: 'Trailers play on the big screen' },
  { icon: '🔥', text: 'Tap emotes to react live' },
  { icon: '🗳️', text: 'Vote yes or no when each one ends. Your vote stays private.' },
  { icon: '⭐', text: 'Everyone says yes: golden buzzer' },
];

function PhoneLobby({ night }) {
  const { s } = night;
  const missing = D.people.filter((p) => !s.seated.includes(p.id));
  return (
    <section className="ps ps--lobby">
      <RoomPill />
      <h1 className="ps-title">You're in.</h1>
      <p className="ps-sub">Sit back. The show starts from the big screen.</p>
      <ol className="howto">
        {HOW_IT_WORKS.map((step) => (
          <li key={step.icon}>
            <span className="howto-icon" aria-hidden="true">
              {step.icon}
            </span>
            {step.text}
          </li>
        ))}
      </ol>
      <div className="crew-strip">
        {D.people.map((p) => {
          const mood = moodOf(p, s);
          return (
            <span key={p.id} className={`crew-member ${s.seated.includes(p.id) ? '' : 'is-away'}`}>
              <span className="crew-avatar">
                <Avatar person={p} s={s} />
                {mood && <span className="crew-mood">{mood.emoji}</span>}
              </span>
              <small>{displayName(p, s)}</small>
            </span>
          );
        })}
      </div>
      <div className="ps-foot">
        <WaitingNote>
          {missing.length
            ? `Waiting for ${listNames(missing.map((p) => p.name))} to join`
            : 'Waiting for the big screen to start the show'}
        </WaitingNote>
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
  const { s, movie, react } = night;
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
        <WaitingNote>Voting opens when the trailer ends</WaitingNote>
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
      <p className="fineprint">Your vote stays private. Everyone has to say yes for the golden buzzer.</p>
    </section>
  );
}

// Shows your own vote and who has voted, never what anyone else picked.
function PhoneWaiting({ night }) {
  const { s, voteCount } = night;
  const mine = s.votes.you;
  const left = D.people.length - voteCount;
  return (
    <section className="ps ps--waiting">
      <div className={`my-vote my-vote--${mine}`}>
        <Icon name={mine === 'yes' ? 'check' : 'cross'} />
      </div>
      <h1 className="ps-title">{mine === 'yes' ? "You're in." : 'You passed.'}</h1>
      <div className="lock-row">
        {D.people.map((p) => (
          <span key={p.id} className={`slot ${s.votes[p.id] ? 'is-locked' : ''}`}>
            <Avatar person={p} s={s} />
            {s.votes[p.id] && <Icon name="lock" />}
          </span>
        ))}
      </div>
      <div className="ps-foot">
        <WaitingNote>{s.phase === 'reveal' ? 'The verdict is on the big screen' : `Waiting on ${left} more`}</WaitingNote>
      </div>
    </section>
  );
}

function PhoneMiss({ night }) {
  const { movie, hasNext } = night;
  return (
    <section className="ps ps--miss">
      <div className="miss-icon" aria-hidden="true">
        🎞️
      </div>
      <p className="eyebrow">{movie.title}</p>
      <h1 className="ps-title">Not this one.</h1>
      <p className="ps-sub">Not everyone was in, so no golden buzzer. Filmocracy is tuning the next pick.</p>
      <div className="ps-foot">
        <div className="countdown" style={{ animationDuration: `${MISS_PAUSE_MS}ms` }} />
        <p className="fineprint">{hasNext ? 'Next trailer coming up…' : "Ranking tonight's picks…"}</p>
      </div>
    </section>
  );
}

function PhoneBuzzer({ night }) {
  const { movie } = night;
  return (
    <section className="ps ps--buzzer">
      <Confetti count={40} />
      <div className="buzzer-btn">
        <Icon name="star" />
      </div>
      <p className="eyebrow">Everyone's in</p>
      <h1 className="buzzer-title gold-text">Golden Buzzer</h1>
      <p className="buzzer-note">
        It's <b>{movie.title}</b> tonight. Grab the popcorn.
      </p>
      <div className="ps-foot">
        <p className="fineprint">Look up: tonight's picks are coming to the big screen.</p>
      </div>
    </section>
  );
}

function PhonePicks({ night }) {
  const top = night.picks.slice(0, 3);
  return (
    <section className="ps ps--picks">
      <p className="eyebrow">Tonight's picks</p>
      <h1 className="ps-title">Your group's top 3</h1>
      <ol className="mini-picks">
        {top.map((p, i) => (
          <li key={p.movie.id}>
            <span className="mini-rank">{i + 1}</span>
            <Poster movie={p.movie} className="poster--thumb" />
            <span className="mini-text">
              <b>{p.movie.title}</b>
              <PickStatus pick={p} />
            </span>
          </li>
        ))}
      </ol>
      <p className="eyebrow ps-label">5 more for your group</p>
      <ol className="mini-recs">
        {D.predicted.map((m) => (
          <li key={m.id}>
            <span>{m.title}</span>
            <b>{m.match}%</b>
          </li>
        ))}
      </ol>
      <div className="ps-foot">
        <WaitingNote>The big screen starts the movie</WaitingNote>
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
      <p className="ps-sub">
        Enjoy {night.s.nowShowing.title}. Filmocracy keeps learning your group's taste every movie night.
      </p>
    </section>
  );
}

const PHONE_SCREENS = {
  scan: PhoneScan,
  mood: PhoneMood,
  connect: PhoneConnect,
  analyzing: PhoneAnalyzing,
  lobby: PhoneLobby,
  react: PhoneReact,
  vote: PhoneVote,
  waiting: PhoneWaiting,
  miss: PhoneMiss,
  buzzer: PhoneBuzzer,
  picks: PhonePicks,
  showing: PhoneShowing,
};
