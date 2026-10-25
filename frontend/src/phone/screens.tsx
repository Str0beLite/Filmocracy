// Phone screens. Onboarding moves on by itself; after that a phone only
// waits, reacts and votes, and follows the big screen through the night.

import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import {
  ArrowRight,
  Check,
  Clapperboard,
  Film,
  Hourglass,
  Lock,
  Popcorn,
  ShieldCheck,
  ScanLine,
  SmilePlus,
  Sparkles,
  Star,
  Vote,
  X,
} from 'lucide-react';
import { http } from '../api/http';
import { rememberProfile } from '../api/profiles';
import { EMOTES, act, movie, type FeelingId, type Snapshot } from '../api';
import { Avatar, Confetti, LivePill, PickSource, Poster, Wildcard, Wordmark } from '../components/ui';
import { FEELING_ICONS } from '../lib/feelings';
import { trailerProgress } from '../lib/night';
import { gsap, useMotion } from '../lib/motion';
import { useRoom, useServerNow } from '../room/useRoom';
import { usePhone } from './usePhone';
import { FeelingStep, MAX_SHOTS, NameStep, READ_MS, ReadingStep, ScreenshotsStep } from './onboarding';

const seatedOf = (s: Snapshot) => s.people.filter((p) => p.seated);

function Top() {
  const { s } = useRoom();
  return (
    <header className="ps-top">
      <Wordmark />
      <LivePill>Room {s.code}</LivePill>
    </header>
  );
}

function WaitingNote({ children }: { children: string }) {
  return (
    <p className="waiting-note" role="status">
      <span className="dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {children}
    </p>
  );
}

// ---- Onboarding ----

// The QR link carries the session's invitation in its fragment. Keep it for
// the join call after sign-in, and drop it from the address bar.
function useInvite() {
  const [invite] = useState(() => {
    const fromLink = new URLSearchParams(location.hash.slice(1)).get('invite');
    if (fromLink) {
      sessionStorage.setItem('tandem.phone.invite', fromLink);
      history.replaceState(null, '', location.pathname);
    }
    return fromLink ?? sessionStorage.getItem('tandem.phone.invite');
  });
  return invite;
}

export function PhoneJoin() {
  const invite = useInvite();
  const { setMe, setFeeling } = usePhone();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function join() {
    setBusy(true);
    setError('');
    try {
      const profile = await http<{ display_name: string | null }>('/profiles/me');
      if (!profile.display_name) { navigate('/phone/name'); return; }
      rememberProfile(profile.display_name);
      const { id } = await act<{ id: string }>('join', { name: profile.display_name });
      setMe(id);
      setFeeling(null);
      navigate('/phone/feeling');
    } catch (err) { setError(err instanceof Error ? err.message : 'Couldn’t join. Try again.'); }
    finally { setBusy(false); }
  }
  return (
    <section className="ps join-page">
      <header className="ps-top join-top">
        <Wordmark />
      </header>
      <div className="join-ticket">
        <div className="join-ticket-body">
          <h1 className="display join-title">
            You’re invited to <em>movie night.</em>
          </h1>
          <div className="join-theater" aria-hidden="true">
            <div className="join-screen" />
            <div className="join-seats">
              {[0, 1, 2].map((seat) => <div className="join-seat" key={seat}>
                <div className="seat-back" /><div className="seat-cushion" />
              </div>)}
            </div>
          </div>
        </div>
        <div className="join-ticket-stub">
          <Vote aria-hidden="true" />
          <p>Your phone is your ballot.<span>Watch together. Vote privately.</span></p>
        </div>
      </div>
      <div className="ps-foot join-foot">
        {invite ? <>
          {error && <p className="field-error" role="alert">{error}</p>}
          <button className="btn btn-primary" disabled={busy} onClick={() => void join()}>
            {busy ? 'Joining…' : 'Join the room'} <ArrowRight aria-hidden="true" />
          </button>
          <p className="fineprint">Your seat is just a tap away.</p>
        </> : <div className="join-scan">
          <ScanLine aria-hidden="true" />
          <p>Scan the QR code on the big screen<span>Use your phone’s camera to join the room.</span></p>
        </div>}
      </div>
    </section>
  );
}

export function PhoneSignIn() {
  return (
    <section className="ps">
      <Top />
      <h1 className="ps-title display">Filmocracy remembers your taste on this phone.</h1>
      <ul className="promise">
        <li>
          <span className="promise-icon">
            <Sparkles aria-hidden="true" />
          </span>
          Next movie night, you skip straight to voting.
        </li>
        <li>
          <span className="promise-icon">
            <ShieldCheck aria-hidden="true" />
          </span>
          Your votes stay private. Nobody sees who said no.
        </li>
      </ul>
      <div className="ps-foot">
        <Link className="btn btn-primary" to="/phone/name">
          Continue <ArrowRight aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

// Your seat's name. Joins the session behind the QR code.
export function PhoneName() {
  const { setMe, setFeeling } = usePhone();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return (
    <NameStep
      top={<Top />}
      sub="It goes on your seat on the big screen."
      cta="Take my seat"
      busy={busy}
      error={error}
      onSubmit={async (name) => {
        setBusy(true);
        try {
          await http('/profiles/me', { display_name: name });
          rememberProfile(name);
          if (!sessionStorage.getItem('tandem.phone.invite')) { navigate('/phone/settings'); return; }
          const { id } = await act<{ id: string }>('join', { name });
          setMe(id);
          setFeeling(null);
          navigate('/phone/feeling');
        } catch (err) {
          setError(
            err instanceof Error && /invitation|ended/i.test(err.message)
              ? 'That room has closed. Scan the QR code on the big screen again.'
              : 'Couldn’t reach the big screen. Check you’re on the same Wi-Fi, then try again.',
          );
        } finally {
          setBusy(false);
        }
      }}
    />
  );
}

export function PhoneFeeling() {
  const [feeling, setFeeling] = useState<FeelingId | null>(null);
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <>
    <FeelingStep top={<Top />} sub="A fresh feeling for this movie night. Your saved taste stays with you."
      feeling={feeling} onPick={setFeeling} busy={busy}
      onContinue={() => {
        if (busy) return;
        setBusy(true);
        setError('');
        void (async () => {
          await act('feeling', { feeling });
          const me = await http<{ feed_id: string | null }>('/me');
          if (me.feed_id) {
            await act('seat', { feedId: me.feed_id });
            navigate('/phone/lobby');
          } else navigate('/phone/screenshots');
        })().catch((err) => setError(err instanceof Error ? err.message : 'Couldn’t save your feeling. Try again.'))
          .finally(() => setBusy(false));
      }} error={error} />
  </>;
}

export function PhoneScreenshots() {
  const { shots, setShots } = usePhone();
  return (
    <ScreenshotsStep
      top={<Top />}
      shots={shots}
      onAdd={(files) => setShots([...shots, ...files.map((f) => URL.createObjectURL(f))].slice(-MAX_SHOTS))}
      next={
        <Link className="btn btn-primary" to="/phone/reading">
          Read my feed <ArrowRight aria-hidden="true" />
        </Link>
      }
      fineprint="Filmocracy only reads the tiles in your screenshots. It never sees your account."
    />
  );
}

export function PhoneReading() {
  const { shots } = usePhone();
  const navigate = useNavigate();
  const [tags, setTags] = useState<string[]>([]);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // Muse reads every tile of every screenshot, which can take a while. Once the
  // tags are in and have had a moment on screen, take the seat; the room takes it from here.
  useEffect(() => {
    let live = true;
    let t: ReturnType<typeof setTimeout>;
    const began = Date.now();
    act<{ tags: string[] }>('feed', { shots })
      .then((r) => {
        if (!live) return;
        setTags(r.tags);
        t = setTimeout(() => act('seat').catch(() => live && setError(true)), Math.max(READ_MS - (Date.now() - began), 2500));
      })
      .catch(() => live && setError(true));
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [shots, attempt]);

  return (
    <ReadingStep
      shots={shots}
      tags={tags}
      error={error}
      onRetry={() => {
        setError(false);
        setAttempt((n) => n + 1);
      }}
      onRepick={() => navigate('/phone/screenshots')}
    />
  );
}

// ---- During the night ----

const HOW_IT_WORKS = [
  { icon: Clapperboard, text: 'Trailers play on the big screen' },
  { icon: SmilePlus, text: 'Tap reactions while they play' },
  { icon: Vote, text: 'Vote yes or no after each one. Your vote stays private.' },
  { icon: Star, text: 'Everyone says yes: golden buzzer' },
];

export function PhoneLobby() {
  const { s } = useRoom();
  const { me } = usePhone();
  const crew = seatedOf(s);
  return (
    <section className="ps">
      <Top />
      <h1 className="ps-title display">You’re in.</h1>
      <p className="ps-sub">Sit back. The show starts from the big screen.</p>
      <ol className="howto">
        {HOW_IT_WORKS.map(({ icon: Icon, text }) => (
          <li key={text}>
            <span className="promise-icon">
              <Icon aria-hidden="true" />
            </span>
            {text}
          </li>
        ))}
      </ol>
      <div className="crew">
        {crew.map((p) => {
          const Icon = p.feeling ? FEELING_ICONS[p.feeling] : null;
          return (
            <span key={p.id} className="crew-member">
              <span className="crew-avatar">
                <Avatar person={p} />
                {Icon && (
                  <span className="crew-feeling">
                    <Icon aria-hidden="true" />
                  </span>
                )}
              </span>
              {p.id === me ? 'You' : p.name}
            </span>
          );
        })}
      </div>
      <div className="ps-foot">
        <WaitingNote>Waiting for the big screen to start the show</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneReact() {
  const { s } = useRoom();
  const { me } = usePhone();
  const now = useServerNow();
  const film = movie(s.movieId!);
  const progress = trailerProgress(s, now);
  const [bursts, setBursts] = useState<{ id: number; idx: number; emoji: string }[]>([]);
  const nextId = useRef(0);
  const send = (idx: number) => {
    const id = nextId.current++;
    setBursts((b) => [...b.slice(-8), { id, idx, emoji: EMOTES[idx].emoji }]);
    navigator.vibrate?.(12);
    act('react', { id: me, emoji: EMOTES[idx].emoji });
  };
  return (
    <section className="ps">
      <div className="now-playing">
        <Poster movie={film} />
        <div className="np-text">
          <p className="np-live">
            {s.pausedAt ? (
              'Paused on the big screen'
            ) : (
              <>
                <span className="live-dot" aria-hidden="true" /> On the big screen
              </>
            )}
          </p>
          <p className="np-title">{film.title}</p>
          <div className="np-progress">
            <i style={{ width: `${progress * 100}%` }} />
          </div>
        </div>
      </div>
      <h1 className="ps-title display vote-q">Watch it tonight?</h1>
      <VoteButtons />
      <div className="emote-row" role="group" aria-label="React on the big screen">
        {EMOTES.map((e, i) => (
          <button key={e.emoji} className="emote" onClick={() => send(i)} aria-label={`React: ${e.label}`}>
            <span aria-hidden="true">{e.emoji}</span>
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
    </section>
  );
}

// I'm in / Pass. Phones can vote during the trailer too: once every seat has
// voted, the backend closes the round and the TV cuts the trailer short.
function VoteButtons() {
  const { s } = useRoom();
  const { me, setMyVote } = usePhone();
  const [sent, setSent] = useState(false);
  const vote = (v: 'yes' | 'no') => {
    setSent(true);
    setMyVote(s.round, v);
    act('vote', { id: me, vote: v }).catch(() => setSent(false));
  };
  return (
    <div className="vote-buttons">
      <button className="vote-btn vote-btn--yes" onClick={() => vote('yes')} disabled={sent}>
        <Check aria-hidden="true" strokeWidth={3} />
        I’m in
      </button>
      <button className="vote-btn vote-btn--no" onClick={() => vote('no')} disabled={sent}>
        <X aria-hidden="true" strokeWidth={3} />
        Pass
      </button>
    </div>
  );
}

export function PhoneVote() {
  const { s } = useRoom();
  const film = movie(s.movieId!);
  return (
    <section className="ps">
      <div className="vote-head">
        <Poster movie={film} />
        <div>
          <p className="vote-title display">{film.title}</p>
          <p className="vote-meta">
            {film.year} · {film.runtime}
          </p>
        </div>
      </div>
      <h1 className="ps-title display vote-q">Watch it tonight?</h1>
      <VoteButtons />
      <p className="fineprint">Your vote stays private. Everyone has to say yes for the golden buzzer.</p>
    </section>
  );
}

// Your own vote, and who has voted. Never what anyone else picked.
export function PhoneVoted() {
  const { s } = useRoom();
  const { myVotes } = usePhone();
  const mine = myVotes[s.round];
  const crew = seatedOf(s);
  const left = crew.filter((p) => !s.locked.includes(p.id)).length;
  return (
    <section className="ps ps--center">
      <div className={`big-mark ${mine ? `big-mark--${mine}` : ''}`}>
        {mine === 'no' ? <X aria-hidden="true" strokeWidth={3} /> : <Check aria-hidden="true" strokeWidth={3} />}
      </div>
      <h1 className="ps-title display">{mine === 'no' ? 'You passed.' : mine ? 'You’re in.' : 'Vote sent.'}</h1>
      <div className="lock-row">
        {crew.map((p) => {
          const locked = s.locked.includes(p.id);
          return (
            <span key={p.id} className={`slot ${locked ? 'is-locked' : ''}`}>
              <Avatar person={p} />
              {locked && <Lock aria-label={`${p.name} voted`} strokeWidth={2.8} />}
            </span>
          );
        })}
      </div>
      <div className="ps-foot">
        <WaitingNote>{(s.phase === 'vote' || s.phase === 'trailer') && left ? `Waiting on ${left} more` : 'The verdict is on the big screen'}</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneMiss() {
  const { s } = useRoom();
  return (
    <section className="ps ps--center">
      <div className="big-mark">
        <Film aria-hidden="true" />
      </div>
      <h1 className="ps-title display">Not this one.</h1>
      <p className="ps-sub">
        Not everyone was in on {movie(s.movieId!).title}, so no golden buzzer. Filmocracy is tuning the next pick.
      </p>
      <div className="ps-foot">
        <WaitingNote>Next trailer coming up</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneCheckpoint() {
  const { s } = useRoom();
  return (
    <section className="ps ps--center">
      <div className="big-mark">
        <Hourglass aria-hidden="true" />
      </div>
      <h1 className="ps-title display">Picks, or more trailers?</h1>
      <p className="ps-sub">{s.round} trailers in and no golden buzzer yet. Look up: the big screen decides what’s next.</p>
      <div className="ps-foot">
        <WaitingNote>Waiting for the big screen</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneBuzzer() {
  const { s } = useRoom();
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap
      .timeline({ defaults: { ease: 'expo.out' } })
      .from('.buzzer-btn', { y: -40, scale: 0.5, autoAlpha: 0, duration: 0.9, ease: 'back.out(2)' })
      .from('.buzzer-title', { scale: 1.6, autoAlpha: 0, duration: 0.8, ease: 'back.out(1.6)' }, 0.25);
  }, scope);
  return (
    <section className="ps ps--center ps--buzzer on-gold" ref={scope}>
      <div className="buzzer-btn" aria-hidden="true">
        <Star fill="currentColor" strokeWidth={0} />
      </div>
      <h1 className="buzzer-title display">Golden Buzzer</h1>
      <p className="buzzer-note">
        Everyone said yes to <b>{movie(s.movieId!).title}</b>.
      </p>
      <div className="ps-foot">
        <p className="fineprint">Look up: the big screen decides what’s next.</p>
      </div>
      <Confetti count={40} />
    </section>
  );
}

export function PhonePicks() {
  const { s } = useRoom();
  const top = s.picks?.top ?? [];
  const more = s.picks?.more ?? [];
  return (
    <section className="ps">
      <h1 className="ps-title display">Your group’s top 3</h1>
      <ol className="mini-picks">
        {top.map((p, i) => {
          const film = movie(p.id);
          return (
            <li key={p.id}>
              <span className="mini-rank">{i + 1}</span>
              <Poster movie={film} />
              <span className="mini-text">
                <b>{film.title}</b>
                <PickSource source={p.source} />
              </span>
            </li>
          );
        })}
      </ol>
      {more.length > 0 && (
        <>
          <h2 className="label">{more.length} more for your group</h2>
          <ol className="mini-recs">
            {more.map((id) => {
              const film = movie(id);
              return (
                <li key={id}>
                  <span>{film.title}</span>
                  {film.wildcard ? <Wildcard /> : film.match !== null && <b>{film.match}%</b>}
                </li>
              );
            })}
          </ol>
        </>
      )}
      <div className="ps-foot">
        <WaitingNote>The big screen starts the movie</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneShowing() {
  const { s } = useRoom();
  const title = s.showingId ? movie(s.showingId).title : 'the movie';
  return (
    <section className="ps ps--center ps--showing on-film">
      <div className="big-mark">
        <Popcorn aria-hidden="true" />
      </div>
      <h1 className="ps-title display">Phone down, eyes up.</h1>
      <p className="ps-sub">Enjoy {title}. Filmocracy learns your group’s taste a little more every movie night.</p>
      <div className="ps-foot" />
    </section>
  );
}
