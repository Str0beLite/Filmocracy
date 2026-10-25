// Big-screen screens. The big screen is the only device that moves the night
// forward; phones wait, react and vote.

import { useRef, type CSSProperties } from 'react';
import { Link, useLoaderData } from 'react-router';
import { ArrowRight, Check, Play, Shuffle, SkipForward, Star } from 'lucide-react';
import type { Picks, Room, Round } from '../api';
import { Avatar, CompletionStatus, Confetti, LivePill, Poster, PickSource, QR, Seat, Wildcard, Wordmark } from '../components/ui';
import { FEELING_ICONS } from '../lib/feelings';
import { CHECKPOINT_EVERY, TRAILER_MS, afterResult, completion, fmtTime, joinUrl } from '../lib/night';
import { gsap, useAutoAdvance, useElapsed, useMotion } from '../lib/motion';

type RoundData = { room: Room; round: Round };

const JOIN_STAGGER_MS = 1400; // mock: friends take their seats one by one

export function TVLobby() {
  const room = useLoaderData() as Room;
  const elapsed = useElapsed(250);
  const seatedCount = Math.min(room.people.length, Math.floor(elapsed / JOIN_STAGGER_MS) + 1);
  const everyone = seatedCount === room.people.length;
  const missing = room.people.length - seatedCount;
  return (
    <section className="tv-view lobby">
      <header className="lobby-top">
        <div className="lobby-brand">
          <Wordmark />
          <LivePill>{room.name}</LivePill>
        </div>
        <CompletionStatus value={completion(0, seatedCount / room.people.length)} />
      </header>

      <div className="lobby-main">
        <div>
          <h1 className="lobby-title display">Grab a seat.</h1>
          <p className="lobby-sub">
            Scan the code, say how you want to feel tonight, and Tandem plays trailers it thinks you’ll all say yes to.
          </p>
          <ol className="lobby-steps">
            <li>
              <b>1</b>Scan
            </li>
            <li>
              <b>2</b>Pick a feeling
            </li>
            <li>
              <b>3</b>Vote on trailers
            </li>
          </ol>
        </div>
        <div className="qr-card">
          <QR text={joinUrl(room.code)} />
          <span className="qr-label">Scan to join</span>
          <span className="qr-code">Room code {room.code}</span>
        </div>
      </div>

      <footer className="lobby-foot">
        <div className="seat-row">
          {room.people.map((p, i) => (
            <Seat key={p.id} person={p} state={i < seatedCount ? 'seated' : 'away'} showFeeling />
          ))}
        </div>
        {everyone ? (
          <Link className="tv-btn tv-btn--primary" to="/tv/trailer/1">
            Start the show <ArrowRight aria-hidden="true" />
          </Link>
        ) : (
          <button className="tv-btn tv-btn--primary" disabled>
            Waiting for {missing} more
          </button>
        )}
      </footer>
    </section>
  );
}

// Placeholder film: three "shots" in the movie's colours, a title card, grain.
function Scene({ round, progress, paused }: { round: Round; progress: number; paused: boolean }) {
  const shot = Math.min(2, Math.floor(progress * 3));
  return (
    <div className={`scene ${paused ? 'is-paused' : ''}`}>
      {['a', 'b', 'c'].map((k, i) => (
        <div key={k} className={`shot shot--${k} ${shot === i ? 'is-on' : ''}`} />
      ))}
      <div className="vignette" />
      <div className="grain" />
      <div className={`title-card ${progress > 0.45 && progress < 0.8 ? 'is-on' : ''}`} aria-hidden="true">
        <p className="display">{round.movie.title}</p>
        <span>{round.movie.year}</span>
      </div>
    </div>
  );
}

function filmStyle(round: Round) {
  const [c1, c2, c3] = round.movie.palette;
  return { '--c1': c1, '--c2': c2, '--c3': c3 } as CSSProperties;
}

const batchPos = (n: number) => ((n - 1) % CHECKPOINT_EVERY) + 1;

// Mock reactions from the room while the trailer plays.
const REACTIONS = [
  { at: 2200, who: 0, emoji: '😂', dx: '-1.5cqw' },
  { at: 3800, who: 1, emoji: '🔥', dx: '1cqw' },
  { at: 5600, who: 2, emoji: '🤯', dx: '-0.5cqw' },
  { at: 7400, who: 0, emoji: '😍', dx: '1.4cqw' },
  { at: 9000, who: 3, emoji: '🔥', dx: '-1cqw' },
];

export function TVTrailer() {
  const { room, round } = useLoaderData() as RoundData;
  const elapsed = useElapsed();
  const progress = Math.min(1, elapsed / TRAILER_MS);
  useAutoAdvance(`/tv/vote/${round.n}`, TRAILER_MS + 300);
  const { movie } = round;
  const byId = Object.fromEntries(room.people.map((p) => [p.id, p]));
  const fits = [...new Set(room.people.map((p) => p.feeling))].filter(Boolean).slice(0, 3);
  return (
    <section className="tv-view trailer on-film" style={filmStyle(round)}>
      <Scene round={round} progress={progress} paused={false} />
      <div className="letterbox letterbox--top" />
      <div className="letterbox letterbox--bottom" />
      <CompletionStatus value={completion(round.n - 1)} className="tv-hud" />

      <div className="trailer-top">
        <span className="chip">
          <Play aria-hidden="true" fill="currentColor" strokeWidth={0} />
          Trailer {batchPos(round.n)} of {CHECKPOINT_EVERY} · <b>{movie.match}% group match</b>
        </span>
      </div>

      <div className="trailer-info">
        <h1 className="trailer-title display">{movie.title}</h1>
        <p className="trailer-meta">
          {movie.year} · {movie.runtime} · {movie.genres.join(', ')}
        </p>
        <div className="why">
          <span className="why-label">Why it’s here</span>
          {movie.wildcard && <Wildcard />}
          {fits.length > 0 && (
            <span className="chip">
              {fits.map((f) => {
                const Icon = FEELING_ICONS[f!];
                return <Icon key={f} aria-hidden="true" />;
              })}
              Fits tonight’s feelings
            </span>
          )}
          {movie.why.map((w) => (
            <span className="chip" key={w.who}>
              <Avatar person={byId[w.who]} />
              {byId[w.who].name}’s feed: {w.tag}
            </span>
          ))}
        </div>
        <div className="progress">
          <div className="progress-track">
            <i style={{ width: `${progress * 100}%` }} />
          </div>
          <span>
            {fmtTime(progress * TRAILER_MS)} / {fmtTime(TRAILER_MS)}
          </span>
          <Link className="tv-btn tv-btn--ghost tv-btn--sm" to={`/tv/vote/${round.n}`}>
            Skip to vote <SkipForward aria-hidden="true" />
          </Link>
        </div>
      </div>

      <div className="trailer-seats">
        {room.people.map((p, i) => (
          <Seat key={p.id} person={p} small>
            {REACTIONS.filter((r) => r.who === i && elapsed >= r.at).map((r) => (
              <span key={r.at} className="reaction" style={{ '--dx': r.dx } as CSSProperties} aria-hidden="true">
                {r.emoji}
              </span>
            ))}
          </Seat>
        ))}
      </div>
    </section>
  );
}

const LOCK_STAGGER_MS = 900; // mock: phones lock in one by one

// Seats only ever show who has voted, never how.
export function TVVote() {
  const { room, round } = useLoaderData() as RoundData;
  const elapsed = useElapsed(150);
  const locked = Math.min(room.people.length, Math.floor(elapsed / LOCK_STAGGER_MS));
  useAutoAdvance(`/tv/reveal/${round.n}`, LOCK_STAGGER_MS * room.people.length + 700);
  return (
    <section className="tv-view trailer on-film" style={filmStyle(round)}>
      <Scene round={round} progress={1} paused />
      <CompletionStatus value={completion(round.n - 1)} className="tv-hud" />
      <div className="verdict">
        <p className="verdict-movie">{round.movie.title}</p>
        <h1 className="verdict-title display">Vote on your phone</h1>
        <div className="seat-row">
          {room.people.map((p, i) => (
            <Seat key={p.id} person={p} state={i < locked ? 'locked' : 'thinking'} />
          ))}
        </div>
        <p className="verdict-sub num">
          {locked} of {room.people.length} locked in
        </p>
      </div>
    </section>
  );
}

const REVEAL_MS = 1900;

export function TVReveal() {
  const { room, round } = useLoaderData() as RoundData;
  useAutoAdvance(afterResult(round.n, round.outcome), REVEAL_MS);
  return (
    <section className="tv-view trailer on-film" style={filmStyle(round)}>
      <Scene round={round} progress={1} paused />
      <CompletionStatus value={completion(round.n - 1)} className="tv-hud" />
      <div className="verdict verdict--reveal">
        <p className="verdict-movie">{round.movie.title}</p>
        <h1 className="verdict-title display">The verdict…</h1>
        <div className="seat-row">
          {room.people.map((p) => (
            <Seat key={p.id} person={p} state="locked" />
          ))}
        </div>
        <p className="verdict-sub">Everyone has to say yes</p>
      </div>
    </section>
  );
}

const MISS_MS = 4500;

export function TVMiss() {
  const { round } = useLoaderData() as RoundData;
  useAutoAdvance(`/tv/trailer/${round.n + 1}`, MISS_MS);
  return (
    <section className="tv-view trailer on-film" style={filmStyle(round)}>
      <Scene round={round} progress={1} paused />
      <CompletionStatus value={completion(round.n)} className="tv-hud" />
      <div className="verdict">
        <p className="verdict-movie">{round.movie.title}</p>
        <h1 className="verdict-title display">Not this one.</h1>
        <p className="verdict-sub">No golden buzzer. Tuning the next pick…</p>
        <div className="countdown" aria-hidden="true">
          <i style={{ animationDuration: `${MISS_MS}ms` }} />
        </div>
      </div>
    </section>
  );
}

export function TVCheckpoint() {
  const { round, watched } = useLoaderData() as RoundData & { watched: Round[] };
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap.from('.watched li', { y: 40, autoAlpha: 0, rotate: -8, stagger: 0.08, duration: 0.9, ease: 'expo.out' });
  }, scope);
  return (
    <section className="tv-view checkpoint" ref={scope}>
      <CompletionStatus value={completion(round.n)} className="tv-hud" />
      <div>
        <h1 className="checkpoint-title display">No golden buzzer yet.</h1>
        <p className="checkpoint-sub">
          That’s {round.n} trailers in. Tandem has learned a lot about your group from those votes, so it can call it
          now or keep looking.
        </p>
        <div className="checkpoint-actions">
          <Link className="tv-btn tv-btn--gold" to="/tv/picks">
            See our picks <ArrowRight aria-hidden="true" />
          </Link>
          <Link className="tv-btn tv-btn--ghost" to={`/tv/trailer/${round.n + 1}`}>
            Keep watching
          </Link>
        </div>
      </div>
      <ul className="watched" aria-label="Trailers watched so far">
        {watched.slice(-6).map((r) => (
          <li key={r.n}>
            <Poster movie={r.movie} />
          </li>
        ))}
        <li className="watched-caption">Tonight so far</li>
      </ul>
    </section>
  );
}

export function TVBuzzer() {
  const { room, round } = useLoaderData() as RoundData;
  const { movie } = round;
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap
      .timeline({ defaults: { ease: 'expo.out' } })
      .fromTo('.buzzer-flash', { autoAlpha: 0.9 }, { autoAlpha: 0, duration: 1.1, ease: 'power2.out' })
      .from('.buzzer-title', { scale: 1.8, autoAlpha: 0, duration: 0.9, ease: 'back.out(1.6)' }, 0.05)
      .from('.buzzer-sub', { y: 16, autoAlpha: 0, duration: 0.6 }, 0.45)
      .from('.buzzer-body .poster', { y: 60, rotate: -6, autoAlpha: 0, duration: 1.1 }, 0.35)
      .from('.buzzer-pick > *', { y: 24, autoAlpha: 0, stagger: 0.07, duration: 0.8 }, 0.55);
  }, scope);
  return (
    <section className="tv-view buzzer on-gold" ref={scope}>
      <div className="buzzer-rays" aria-hidden="true" />
      <Confetti count={90} />
      <div className="buzzer-flash" aria-hidden="true" />
      <CompletionStatus value={100} className="tv-hud" />
      <header className="buzzer-head">
        <h1 className="buzzer-title display">Golden Buzzer</h1>
        <p className="buzzer-sub">Everyone said yes.</p>
      </header>
      <div className="buzzer-body">
        <Poster movie={movie} />
        <div className="buzzer-pick">
          <h2 className="display">{movie.title}</h2>
          <p className="buzzer-meta">
            {movie.year} · {movie.runtime} · {movie.genres.join(', ')}
          </p>
          <p className="buzzer-logline">{movie.logline}</p>
          <div className="buzzer-crew">
            {room.people.map((p) => (
              <span key={p.id}>
                <Avatar person={p} />
                <Check aria-hidden="true" strokeWidth={3.5} />
              </span>
            ))}
          </div>
          <div className="buzzer-actions">
            <Link className="tv-btn tv-btn--gold" to="/tv/picks">
              See tonight’s picks <ArrowRight aria-hidden="true" />
            </Link>
            <Link className="tv-btn tv-btn--ghost" to={`/tv/trailer/${round.n + 1}`}>
              Keep browsing
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export function TVPicks() {
  const { picks } = useLoaderData() as { picks: Picks };
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap
      .timeline({ defaults: { ease: 'expo.out' } })
      .from('.picks-head > *', { y: 20, autoAlpha: 0, stagger: 0.08, duration: 0.8 })
      .from('.pick', { y: 50, autoAlpha: 0, stagger: { each: 0.12, from: 'start' }, duration: 1 }, 0.15)
      .from('.pick--first', { scale: 0.94, duration: 1.2, ease: 'expo.out' }, 0.25)
      .from('.rec', { y: 24, autoAlpha: 0, stagger: 0.06, duration: 0.7 }, 0.55);
  }, scope);
  const [first] = picks.top;
  return (
    <section className="tv-view picks" ref={scope}>
      <CompletionStatus value={100} className="tv-hud" />
      <header className="picks-head">
        <div>
          <h1 className="picks-title display">Your group’s top 3</h1>
          <p className="picks-sub">Golden buzzers first, then the trailers you liked, then what Tandem predicts.</p>
        </div>
        <Link className="tv-btn tv-btn--gold" to={`/tv/showing/${first.movie.id}`}>
          <Play aria-hidden="true" fill="currentColor" strokeWidth={0} /> Start #1
        </Link>
      </header>

      <ol className="podium">
        {picks.top.map((p, i) => (
          <li key={p.movie.id} className={`pick ${i === 0 ? 'pick--first' : ''}`}>
            <Poster movie={p.movie} />
            <div className="pick-info">
              <span className="pick-rank">{i + 1}</span>
              <h3 className="display">{p.movie.title}</h3>
              <p className="pick-meta">
                {p.movie.year} · {p.movie.genres.join(', ')}
              </p>
              {p.movie.wildcard && <Wildcard />}
              <PickSource source={p.source} />
            </div>
          </li>
        ))}
      </ol>

      <div>
        <h2 className="recs-title display">5 more for your group</h2>
        <ol className="recs-row">
          {picks.more.map((m) => (
            <li key={m.id} className="rec">
              <Poster movie={m} />
              <div className="rec-text">
                <b>{m.title}</b>
                {m.wildcard ? (
                  <span className="wildcard">
                    <Shuffle aria-hidden="true" /> Wildcard
                  </span>
                ) : (
                  <span>{m.match}% match</span>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export function TVShowing() {
  const { title } = useLoaderData() as { title: string };
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap
      .timeline()
      .from('.showing-label', { autoAlpha: 0, duration: 1.2 }, 0.3)
      .from('.showing h1', { autoAlpha: 0, scale: 1.04, filter: 'blur(12px)', duration: 2.2, ease: 'power2.out' }, 0.6)
      .from('.showing-sub', { autoAlpha: 0, duration: 1.4 }, 1.8);
  }, scope);
  return (
    <section className="tv-view showing on-film" ref={scope}>
      <p className="showing-label">
        <Star aria-hidden="true" size="1em" fill="currentColor" strokeWidth={0} /> Now showing
      </p>
      <h1 className="display">{title}</h1>
      <p className="showing-sub">Lights down. Phones away.</p>
    </section>
  );
}
