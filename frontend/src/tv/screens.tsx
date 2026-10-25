// Big-screen screens, drawn from the live room. The big screen is the only
// device that moves the night forward; phones wait, react and vote.

import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { ArrowRight, Check, Play, RotateCcw, SkipForward, Star } from 'lucide-react';
import { CHECKPOINT_EVERY, FEELINGS, MISS_MS, act, movie, type Movie, type Snapshot } from '../api';
import { ActionButton, Avatar, CompletionStatus, Confetti, LivePill, PickSource, Poster, QR, Seat, Wildcard, Wordmark } from '../components/ui';
import { FEELING_ICONS } from '../lib/feelings';
import { completion, fmtTime, joinUrl } from '../lib/night';
import { gsap, useMotion } from '../lib/motion';
import { useTrailer } from '../api/tmdb';
import { useRoom, useServerNow } from '../room/useRoom';

const seatedOf = (s: Snapshot) => s.people.filter((p) => p.seated);

export function TVLobby() {
  const { s } = useRoom();
  const seated = seatedOf(s);
  const joining = s.people.length - seated.length;
  return (
    <section className="tv-view lobby">
      <header className="lobby-top">
        <div className="lobby-brand">
          <Wordmark />
          <LivePill>{s.name}</LivePill>
        </div>
        <CompletionStatus value={completion(s)} />
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
          <QR text={joinUrl(s.code)} />
          <span className="qr-label">Scan to join</span>
          <span className="qr-code">Room code {s.code}</span>
        </div>
      </div>

      <footer className="lobby-foot">
        <div className="seat-row">
          {s.people.length === 0 && <p className="lobby-empty">Seats fill up as phones join.</p>}
          {s.people.map((p) => (
            <Seat key={p.id} person={p} state={p.seated ? 'seated' : 'joining'} showFeeling />
          ))}
        </div>
        <div className="lobby-go">
          {joining > 0 && seated.length > 0 && <span className="lobby-note">{joining} still joining</span>}
          <ActionButton action="start" className="tv-btn tv-btn--primary" disabled={!seated.length}>
            {seated.length ? (
              <>
                Start the show <ArrowRight aria-hidden="true" />
              </>
            ) : (
              'Waiting for someone to join'
            )}
          </ActionButton>
        </div>
      </footer>
    </section>
  );
}

// Placeholder film: three "shots" in the movie's colours, a title card, grain.
function Scene({ film, progress, paused }: { film: Movie; progress: number; paused: boolean }) {
  const shot = Math.min(2, Math.floor(progress * 3));
  return (
    <div className={`scene ${paused ? 'is-paused' : ''}`}>
      {['a', 'b', 'c'].map((k, i) => (
        <div key={k} className={`shot shot--${k} ${shot === i ? 'is-on' : ''}`} />
      ))}
      <div className="vignette" />
      <div className="grain" />
      <div className={`title-card ${progress > 0.45 && progress < 0.8 ? 'is-on' : ''}`} aria-hidden="true">
        <p className="display">{film.title}</p>
        <span>{film.year}</span>
      </div>
    </div>
  );
}

const YT = 'https://www.youtube-nocookie.com';

// The real trailer (a YouTube key from TMDB), played to its end. Listens to the
// embed's postMessage events: once it plays, the night is timed to the video;
// when it ends, voting opens. onFail drops back to the placeholder scene.
function TrailerVideo({ film, ytKey, round, onFail }: { film: Movie; ytKey: string; round: number; onFail: () => void }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const timed = useRef(false);
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== YT || e.source !== frame.current?.contentWindow) return;
      let msg: { event?: string; info?: { playerState?: number; currentTime?: number; duration?: number } | number };
      try {
        msg = JSON.parse(e.data);
      } catch {
        return;
      }
      const info = typeof msg.info === 'object' ? msg.info : undefined;
      if (msg.event === 'onError') onFail();
      if (info?.playerState === 1 && info.duration && !timed.current) {
        timed.current = true;
        act('trailerPlaying', { round, ms: info.duration * 1000, at: (info.currentTime ?? 0) * 1000 });
      }
      if (info?.playerState === 0 || (msg.event === 'onStateChange' && msg.info === 0)) {
        act('endTrailer', { round });
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [round, onFail]);
  const listen = () =>
    frame.current?.contentWindow?.postMessage(JSON.stringify({ event: 'listening', id: 1, channel: 'widget' }), YT);
  return (
    <div className="scene">
      <iframe
        ref={frame}
        className="scene-video"
        src={`${YT}/embed/${ytKey}?autoplay=1&controls=0&rel=0&playsinline=1&iv_load_policy=3&enablejsapi=1&origin=${encodeURIComponent(location.origin)}`}
        title={`${film.title} trailer`}
        allow="autoplay; encrypted-media"
        tabIndex={-1}
        onLoad={listen}
      />
    </div>
  );
}

function filmStyle(film: Movie) {
  const [c1, c2, c3] = film.palette;
  return { '--c1': c1, '--c2': c2, '--c3': c3 } as CSSProperties;
}

const batchPos = (n: number) => ((n - 1) % CHECKPOINT_EVERY) + 1;

export function TVTrailer() {
  const { s } = useRoom();
  const now = useServerNow();
  const film = movie(s.movieId!);
  const trailer = useTrailer(film.tmdbId);
  const [failed, setFailed] = useState<string | null>(null);
  const onFail = useCallback(() => setFailed(trailer), [trailer]);
  const progress = Math.min(1, Math.max(0, (now - (s.trailerStartedAt ?? now)) / s.trailerMs));
  const seated = seatedOf(s);
  const byId = Object.fromEntries(s.people.map((p) => [p.id, p]));
  // Feelings in the room that this film's tags actually match.
  const fits = FEELINGS.filter(
    (f) => seated.some((p) => p.feeling === f.id) && f.boost.some((t) => film.tags.includes(t)),
  );
  return (
    <section className="tv-view trailer on-film" style={filmStyle(film)}>
      {trailer && failed !== trailer ? (
        <TrailerVideo key={s.round} film={film} ytKey={trailer} round={s.round} onFail={onFail} />
      ) : (
        <Scene film={film} progress={progress} paused={false} />
      )}
      <div className="letterbox letterbox--top" />
      <div className="letterbox letterbox--bottom" />
      <CompletionStatus value={completion(s)} className="tv-hud" />

      <div className="trailer-top">
        <span className="chip">
          <Play aria-hidden="true" fill="currentColor" strokeWidth={0} />
          Trailer {batchPos(s.round)} of {CHECKPOINT_EVERY} · <b>{film.match}% group match</b>
        </span>
      </div>

      <div className="trailer-info">
        <h1 className="trailer-title display">{film.title}</h1>
        <p className="trailer-meta">
          {film.year} · {film.runtime} · {film.genres.join(', ')}
        </p>
        <div className="why">
          <span className="why-label">Why it’s here</span>
          {film.wildcard && <Wildcard />}
          {fits.length > 0 && (
            <span className="chip">
              {fits.map((f) => {
                const Icon = FEELING_ICONS[f.id];
                return <Icon key={f.id} aria-hidden="true" />;
              })}
              Fits tonight’s {fits.length > 1 ? 'feelings' : 'feeling'}
            </span>
          )}
          {s.why
            .filter((w) => byId[w.who])
            .map((w) => (
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
            {fmtTime(progress * s.trailerMs)} / {fmtTime(s.trailerMs)}
          </span>
          <ActionButton action="endTrailer" className="tv-btn tv-btn--ghost tv-btn--sm">
            Skip to vote <SkipForward aria-hidden="true" />
          </ActionButton>
        </div>
      </div>

      <div className="trailer-seats">
        {seated.map((p) => (
          <Seat key={p.id} person={p} small>
            {s.reactions
              .filter((r) => r.who === p.id)
              .map((r) => (
                <span
                  key={r.id}
                  className="reaction"
                  style={{ '--dx': `${(r.id % 5) - 2}cqw` } as CSSProperties}
                  aria-hidden="true"
                >
                  {r.emoji}
                </span>
              ))}
          </Seat>
        ))}
      </div>
    </section>
  );
}

// Seats only ever show who has voted, never how.
export function TVVote() {
  const { s } = useRoom();
  const film = movie(s.movieId!);
  const seated = seatedOf(s);
  const locked = seated.filter((p) => s.locked.includes(p.id)).length;
  return (
    <section className="tv-view trailer on-film" style={filmStyle(film)}>
      <Scene film={film} progress={1} paused />
      <CompletionStatus value={completion(s)} className="tv-hud" />
      <div className="verdict">
        <p className="verdict-movie">{film.title}</p>
        <h1 className="verdict-title display">Vote on your phone</h1>
        <div className="seat-row">
          {seated.map((p) => (
            <Seat key={p.id} person={p} state={s.locked.includes(p.id) ? 'locked' : 'thinking'} />
          ))}
        </div>
        <p className="verdict-sub num">
          {locked} of {seated.length} locked in
        </p>
      </div>
    </section>
  );
}

export function TVReveal() {
  const { s } = useRoom();
  const film = movie(s.movieId!);
  return (
    <section className="tv-view trailer on-film" style={filmStyle(film)}>
      <Scene film={film} progress={1} paused />
      <CompletionStatus value={completion(s)} className="tv-hud" />
      <div className="verdict verdict--reveal">
        <p className="verdict-movie">{film.title}</p>
        <h1 className="verdict-title display">The verdict…</h1>
        <div className="seat-row">
          {seatedOf(s).map((p) => (
            <Seat key={p.id} person={p} state="locked" />
          ))}
        </div>
        <p className="verdict-sub">Everyone has to say yes</p>
      </div>
    </section>
  );
}

export function TVMiss() {
  const { s } = useRoom();
  const film = movie(s.movieId!);
  return (
    <section className="tv-view trailer on-film" style={filmStyle(film)}>
      <Scene film={film} progress={1} paused />
      <CompletionStatus value={completion(s)} className="tv-hud" />
      <div className="verdict">
        <p className="verdict-movie">{film.title}</p>
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
  const { s } = useRoom();
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap.from('.watched li', { y: 40, autoAlpha: 0, rotate: -8, stagger: 0.08, duration: 0.9, ease: 'expo.out' });
  }, scope);
  return (
    <section className="tv-view checkpoint" ref={scope}>
      <CompletionStatus value={completion(s)} className="tv-hud" />
      <div>
        <h1 className="checkpoint-title display">No golden buzzer yet.</h1>
        <p className="checkpoint-sub">
          That’s {s.round} trailers in. Tandem has learned a lot about your group from those votes, so it can call it now
          or keep looking.
        </p>
        <div className="checkpoint-actions">
          <ActionButton action="picks" className="tv-btn tv-btn--gold">
            See our picks <ArrowRight aria-hidden="true" />
          </ActionButton>
          <ActionButton action="next" className="tv-btn tv-btn--ghost">
            Keep watching
          </ActionButton>
        </div>
      </div>
      <ul className="watched" aria-label="Trailers watched so far">
        {s.shown.slice(-6).map((id, i) => (
          <li key={`${id}-${i}`}>
            <Poster movie={movie(id)} />
          </li>
        ))}
        <li className="watched-caption">Tonight so far</li>
      </ul>
    </section>
  );
}

export function TVBuzzer() {
  const { s } = useRoom();
  const film = movie(s.movieId!);
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
        <Poster movie={film} />
        <div className="buzzer-pick">
          <h2 className="display">{film.title}</h2>
          <p className="buzzer-meta">
            {film.year} · {film.runtime} · {film.genres.join(', ')}
          </p>
          <p className="buzzer-logline">{film.logline}</p>
          <div className="buzzer-crew">
            {seatedOf(s).map((p) => (
              <span key={p.id}>
                <Avatar person={p} />
                <Check aria-hidden="true" strokeWidth={3.5} />
              </span>
            ))}
          </div>
          <div className="buzzer-actions">
            <ActionButton action="picks" className="tv-btn tv-btn--gold">
              See tonight’s picks <ArrowRight aria-hidden="true" />
            </ActionButton>
            <ActionButton action="next" className="tv-btn tv-btn--ghost">
              Keep browsing
            </ActionButton>
          </div>
        </div>
      </div>
    </section>
  );
}

export function TVPicks() {
  const { s } = useRoom();
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap
      .timeline({ defaults: { ease: 'expo.out' } })
      .from('.picks-head > *', { y: 20, autoAlpha: 0, stagger: 0.08, duration: 0.8 })
      .from('.pick', { y: 50, autoAlpha: 0, stagger: 0.12, duration: 1 }, 0.15)
      .from('.pick--first', { scale: 0.94, duration: 1.2 }, 0.25)
      .from('.rec', { y: 24, autoAlpha: 0, stagger: 0.06, duration: 0.7 }, 0.55);
  }, scope);
  const top = s.picks?.top ?? [];
  const more = s.picks?.more ?? [];
  return (
    <section className="tv-view picks" ref={scope}>
      <CompletionStatus value={100} className="tv-hud" />
      <header className="picks-head">
        <div>
          <h1 className="picks-title display">Your group’s top 3</h1>
          <p className="picks-sub">Golden buzzers first, then the trailers you liked, then what Tandem predicts.</p>
        </div>
        {top[0] && (
          <ActionButton action="showing" body={{ id: top[0].id }} className="tv-btn tv-btn--gold">
            <Play aria-hidden="true" fill="currentColor" strokeWidth={0} /> Start #1
          </ActionButton>
        )}
      </header>

      <ol className="podium">
        {top.map((p, i) => {
          const film = movie(p.id);
          return (
            <li key={p.id} className={`pick ${i === 0 ? 'pick--first' : ''}`}>
              <Poster movie={film} />
              <div className="pick-info">
                <span className="pick-rank">{i + 1}</span>
                <h3 className="display">{film.title}</h3>
                <p className="pick-meta">
                  {film.year} · {film.genres.join(', ')}
                </p>
                {film.wildcard && <Wildcard />}
                <PickSource source={p.source} />
              </div>
            </li>
          );
        })}
      </ol>

      {more.length > 0 && (
        <div>
          <h2 className="recs-title display">{more.length} more for your group</h2>
          <ol className="recs-row">
            {more.map((id) => {
              const film = movie(id);
              return (
                <li key={id} className="rec">
                  <Poster movie={film} />
                  <div className="rec-text">
                    <b>{film.title}</b>
                    {film.wildcard ? <Wildcard /> : <span>{film.match}% match</span>}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </section>
  );
}

export function TVShowing() {
  const { s } = useRoom();
  const title = s.showingId ? movie(s.showingId).title : '';
  const scope = useRef<HTMLElement>(null);
  useMotion(() => {
    gsap
      .timeline()
      .from('.showing-label', { autoAlpha: 0, duration: 1.2 }, 0.3)
      .from('.showing h1', { autoAlpha: 0, scale: 1.04, filter: 'blur(12px)', duration: 2.2, ease: 'power2.out' }, 0.6)
      .from('.showing-sub, .showing-again', { autoAlpha: 0, duration: 1.4 }, 1.8);
  }, scope);
  return (
    <section className="tv-view showing on-film" ref={scope}>
      <p className="showing-label">
        <Star aria-hidden="true" size="1em" fill="currentColor" strokeWidth={0} /> Now showing
      </p>
      <h1 className="display">{title}</h1>
      <p className="showing-sub">Lights down. Phones away.</p>
      <ActionButton action="newNight" className="tv-btn tv-btn--ghost tv-btn--sm showing-again">
        <RotateCcw aria-hidden="true" /> New night, same crew
      </ActionButton>
    </section>
  );
}
