// Phone screens. Onboarding moves on by itself; after that a phone only
// waits, reacts and votes. The big screen moves the night forward.

import { useRef, useState, type ChangeEvent } from 'react';
import { Link, useLoaderData, useNavigate, useSearchParams } from 'react-router';
import {
  ArrowRight,
  Check,
  Clapperboard,
  Film,
  Hourglass,
  ImagePlus,
  Lock,
  Popcorn,
  ShieldCheck,
  SmilePlus,
  Sparkles,
  Star,
  Vote,
  X,
} from 'lucide-react';
import { EMOTES, FEELINGS, ME_ID, type Person, type Picks, type Room, type Round } from '../api';
import { Avatar, Confetti, LivePill, PickSource, Poster, Seat, Wildcard, Wordmark } from '../components/ui';
import { FEELING_ICONS } from '../lib/feelings';
import { TRAILER_MS } from '../lib/night';
import { gsap, useAutoAdvance, useElapsed, useMotion } from '../lib/motion';
import { usePhone } from './usePhone';

type RoundData = { room: Room; round: Round };

// This phone's person, with what they picked during onboarding.
function useMe(room: Room): Person {
  const { feeling } = usePhone();
  const me = room.people.find((p) => p.id === ME_ID)!;
  return { ...me, feeling: feeling ?? me.feeling };
}

function useCrew(room: Room) {
  const me = useMe(room);
  return room.people.map((p) => (p.id === ME_ID ? me : p));
}

function Top({ room }: { room: Room }) {
  return (
    <header className="ps-top">
      <Wordmark />
      <LivePill>Room {room.code}</LivePill>
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

export function PhoneJoin() {
  const room = useLoaderData() as Room;
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const scanned = params.get('room')?.toUpperCase() === room.code;
  const [code, setCode] = useState('');
  return (
    <section className="ps">
      <header className="ps-top">
        <Wordmark />
      </header>
      <div className="join-hero" aria-hidden="true">
        <div className="seat-row">
          {room.people.map((p) => (
            <Seat key={p.id} person={p} />
          ))}
        </div>
      </div>
      {scanned ? (
        <>
          <h1 className="ps-title display">You’re invited to movie night.</h1>
          <div className="join-room">
            <b>{room.name}</b>
            <span>Room {room.code} · on the big screen</span>
          </div>
          <div className="ps-foot">
            <Link className="btn btn-primary" to="/phone/sign-in">
              Join the room <ArrowRight aria-hidden="true" />
            </Link>
          </div>
        </>
      ) : (
        <form
          style={{ display: 'contents' }}
          onSubmit={(e) => {
            e.preventDefault();
            if (code.length === 4) navigate('/phone/sign-in');
          }}
        >
          <h1 className="ps-title display">Join movie night</h1>
          <p className="ps-sub">Scan the code on the big screen, or type the room code under it.</p>
          <label className="field">
            Room code
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^a-z0-9]/gi, '').slice(0, 4))}
              placeholder="K7Q2…"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              inputMode="text"
              name="room"
            />
          </label>
          <div className="ps-foot">
            <button className="btn btn-primary" disabled={code.length !== 4}>
              Join the room <ArrowRight aria-hidden="true" />
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function GoogleG() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

export function PhoneSignIn() {
  const room = useLoaderData() as Room;
  return (
    <section className="ps">
      <Top room={room} />
      <h1 className="ps-title display">Sign in once, and Tandem remembers your taste.</h1>
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
        <Link className="btn btn-google" to="/phone/feeling">
          <GoogleG /> Sign in with Google
        </Link>
      </div>
    </section>
  );
}

export function PhoneFeeling() {
  const room = useLoaderData() as Room;
  const { feeling, setFeeling } = usePhone();
  return (
    <section className="ps">
      <Top room={room} />
      <h1 className="ps-title display">How do you want to feel tonight?</h1>
      <p className="ps-sub">Tandem blends everyone’s answer into what it picks.</p>
      <div className="feeling-grid" role="radiogroup" aria-label="Tonight’s feeling">
        {FEELINGS.map((f) => {
          const Icon = FEELING_ICONS[f.id];
          return (
            <button key={f.id} role="radio" aria-checked={feeling === f.id} className="feeling" onClick={() => setFeeling(f.id)}>
              <Icon aria-hidden="true" />
              {f.label}
            </button>
          );
        })}
      </div>
      <div className="ps-foot">
        <Link
          className="btn btn-primary"
          to="/phone/screenshots"
          aria-disabled={!feeling}
          onClick={(e) => !feeling && e.preventDefault()}
        >
          Continue <ArrowRight aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

const SHOTS_NEEDED = 3;

export function PhoneScreenshots() {
  const room = useLoaderData() as Room;
  const { shots, setShots } = usePhone();
  const input = useRef<HTMLInputElement>(null);
  const done = shots.length >= SHOTS_NEEDED;

  const add = (e: ChangeEvent<HTMLInputElement>) => {
    const urls = [...(e.target.files ?? [])].map((f) => URL.createObjectURL(f));
    setShots([...shots, ...urls].slice(-SHOTS_NEEDED));
    e.target.value = '';
  };

  return (
    <section className="ps">
      <Top room={room} />
      <h1 className="ps-title display">Show us your Explore page.</h1>
      <ol className="howto-shots">
        <li>Open Instagram and tap the search tab.</li>
        <li>Scroll a little, then take a screenshot.</li>
        <li>Do that 3 times, then add them here.</li>
      </ol>
      <div className="shots">
        {Array.from({ length: SHOTS_NEEDED }, (_, i) => (
          <div key={i} className={`shot-slot ${shots[i] ? 'is-filled' : ''} ${i === shots.length ? 'is-next' : ''}`}>
            {shots[i] ? <img src={shots[i]} alt={`Screenshot ${i + 1}`} width={90} height={160} /> : <ImagePlus aria-hidden="true" />}
          </div>
        ))}
      </div>
      <div className="ps-foot">
        {done ? (
          <Link className="btn btn-primary" to="/phone/reading">
            Read my feed <ArrowRight aria-hidden="true" />
          </Link>
        ) : (
          <>
            <input
              ref={input}
              id="shots"
              className="file-input"
              type="file"
              accept="image/*"
              multiple
              onChange={add}
            />
            <button className="btn btn-primary" onClick={() => input.current?.click()}>
              <ImagePlus aria-hidden="true" />
              {shots.length ? `Add ${SHOTS_NEEDED - shots.length} more` : 'Add screenshots'}
            </button>
          </>
        )}
        <p className="fineprint">Tandem only reads the tiles in your screenshots. It never sees your account.</p>
      </div>
    </section>
  );
}

const READ_MS = 5200;

export function PhoneReading() {
  const tags = useLoaderData() as string[];
  const { shots } = usePhone();
  const elapsed = useElapsed(150);
  const shown = tags.filter((_, i) => elapsed > 700 + i * 650);
  useAutoAdvance('/phone/lobby', READ_MS);
  const finished = shown.length === tags.length;
  return (
    <section className="ps ps--center">
      <div className="reading-shots" aria-hidden="true">
        {Array.from({ length: SHOTS_NEEDED }, (_, i) => (
          <div key={i} className="reading-shot">
            {shots[i] && <img src={shots[i]} alt="" width={74} height={132} />}
          </div>
        ))}
      </div>
      <h1 className="ps-title display">{finished ? 'Got your vibe.' : 'Reading your Explore page…'}</h1>
      <p className="ps-sub">Tandem turns what your feed is full of into movie taste.</p>
      <ul className="tags" aria-live="polite">
        {shown.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      <div className="ps-foot" />
    </section>
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
  const room = useLoaderData() as Room;
  const crew = useCrew(room);
  return (
    <section className="ps">
      <Top room={room} />
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
              {p.id === ME_ID ? 'You' : p.name}
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
  const { round } = useLoaderData() as RoundData;
  const progress = Math.min(1, useElapsed() / TRAILER_MS);
  const [bursts, setBursts] = useState<{ id: number; idx: number; emoji: string }[]>([]);
  const nextId = useRef(0);
  const send = (idx: number) => {
    const id = nextId.current++;
    setBursts((b) => [...b.slice(-8), { id, idx, emoji: EMOTES[idx].emoji }]);
    navigator.vibrate?.(12);
  };
  return (
    <section className="ps">
      <div className="now-playing">
        <Poster movie={round.movie} />
        <div className="np-text">
          <p className="np-live">
            <span className="live-dot" aria-hidden="true" /> On the big screen
          </p>
          <p className="np-title">{round.movie.title}</p>
          <div className="np-progress">
            <i style={{ width: `${progress * 100}%` }} />
          </div>
        </div>
      </div>
      <h1 className="label">React on the big screen</h1>
      <div className="emote-grid">
        {EMOTES.map((e, i) => (
          <button key={e.emoji} className="emote" onClick={() => send(i)} aria-label={`React: ${e.label}`}>
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

export function PhoneVote() {
  const { round } = useLoaderData() as RoundData;
  const { movie } = round;
  return (
    <section className="ps">
      <div className="vote-head">
        <Poster movie={movie} />
        <div>
          <p className="vote-title display">{movie.title}</p>
          <p className="vote-meta">
            {movie.year} · {movie.runtime}
          </p>
        </div>
      </div>
      <h1 className="ps-title display vote-q">Watch it tonight?</h1>
      <div className="vote-buttons">
        <Link className="vote-btn vote-btn--yes" to={`/phone/voted/${round.n}?vote=yes`} replace>
          <Check aria-hidden="true" strokeWidth={3} />
          I’m in
        </Link>
        <Link className="vote-btn vote-btn--no" to={`/phone/voted/${round.n}?vote=no`} replace>
          <X aria-hidden="true" strokeWidth={3} />
          Pass
        </Link>
      </div>
      <p className="fineprint">Your vote stays private. Everyone has to say yes for the golden buzzer.</p>
    </section>
  );
}

const LOCK_STAGGER_MS = 900;

// Your own vote, and who has voted. Never what anyone else picked.
export function PhoneVoted() {
  const { room } = useLoaderData() as RoundData;
  const [params] = useSearchParams();
  const yes = params.get('vote') !== 'no';
  const crew = useCrew(room);
  const elapsed = useElapsed(150);
  const others = crew.filter((p) => p.id !== ME_ID);
  const lockedOthers = Math.min(others.length, Math.floor(elapsed / LOCK_STAGGER_MS));
  const isLocked = (p: Person) => p.id === ME_ID || others.indexOf(p) < lockedOthers;
  const left = others.length - lockedOthers;
  return (
    <section className="ps ps--center">
      <div className={`big-mark big-mark--${yes ? 'yes' : 'no'}`}>
        {yes ? <Check aria-hidden="true" strokeWidth={3} /> : <X aria-hidden="true" strokeWidth={3} />}
      </div>
      <h1 className="ps-title display">{yes ? "You’re in." : 'You passed.'}</h1>
      <div className="lock-row">
        {crew.map((p) => (
          <span key={p.id} className={`slot ${isLocked(p) ? 'is-locked' : ''}`}>
            <Avatar person={p} />
            {isLocked(p) && <Lock aria-label={`${p.name} voted`} strokeWidth={2.8} />}
          </span>
        ))}
      </div>
      <div className="ps-foot">
        <WaitingNote>{left ? `Waiting on ${left} more` : 'The verdict is on the big screen'}</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneMiss() {
  const { round } = useLoaderData() as RoundData;
  return (
    <section className="ps ps--center">
      <div className="big-mark">
        <Film aria-hidden="true" />
      </div>
      <h1 className="ps-title display">Not this one.</h1>
      <p className="ps-sub">Not everyone was in on {round.movie.title}, so no golden buzzer. Tandem is tuning the next pick.</p>
      <div className="ps-foot">
        <WaitingNote>Next trailer coming up</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneCheckpoint() {
  const { round } = useLoaderData() as RoundData;
  return (
    <section className="ps ps--center">
      <div className="big-mark">
        <Hourglass aria-hidden="true" />
      </div>
      <h1 className="ps-title display">Picks, or more trailers?</h1>
      <p className="ps-sub">{round.n} trailers in and no golden buzzer yet. Look up: the big screen decides what’s next.</p>
      <div className="ps-foot">
        <WaitingNote>Waiting for the big screen</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneBuzzer() {
  const { round } = useLoaderData() as RoundData;
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
        Everyone said yes to <b>{round.movie.title}</b>.
      </p>
      <div className="ps-foot">
        <p className="fineprint">Look up: tonight’s picks are coming to the big screen.</p>
      </div>
      <Confetti count={40} />
    </section>
  );
}

export function PhonePicks() {
  const { picks } = useLoaderData() as { picks: Picks };
  return (
    <section className="ps">
      <h1 className="ps-title display">Your group’s top 3</h1>
      <ol className="mini-picks">
        {picks.top.map((p, i) => (
          <li key={p.movie.id}>
            <span className="mini-rank">{i + 1}</span>
            <Poster movie={p.movie} />
            <span className="mini-text">
              <b>{p.movie.title}</b>
              <PickSource source={p.source} />
            </span>
          </li>
        ))}
      </ol>
      <h2 className="label">5 more for your group</h2>
      <ol className="mini-recs">
        {picks.more.map((m) => (
          <li key={m.id}>
            <span>{m.title}</span>
            {m.wildcard ? <Wildcard /> : <b>{m.match}%</b>}
          </li>
        ))}
      </ol>
      <div className="ps-foot">
        <WaitingNote>The big screen starts the movie</WaitingNote>
      </div>
    </section>
  );
}

export function PhoneShowing() {
  const { title } = useLoaderData() as { title: string };
  return (
    <section className="ps ps--center ps--showing on-film">
      <div className="big-mark">
        <Popcorn aria-hidden="true" />
      </div>
      <h1 className="ps-title display">Phone down, eyes up.</h1>
      <p className="ps-sub">Enjoy {title}. Tandem learns your group’s taste a little more every movie night.</p>
      <div className="ps-foot" />
    </section>
  );
}
