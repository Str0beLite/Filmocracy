import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { ApiError, http } from '../api/http';
import { useTrailer } from '../api/tmdb';
import { FEELINGS } from '../api/data';
import type { FeelingId } from '../api';
import { Wordmark } from '../components/ui';
import { gsap, useMotion } from '../lib/motion';
import { FeelingStep, NameStep, READ_MS, ReadingStep, ScreenshotsStep } from '../phone/onboarding';
import './training.css';

type Step = 'loading' | 'name' | 'feeling' | 'screenshots' | 'reading' | 'watch' | 'done';
interface Recommendation {
  rec_id: number;
  score?: number;
  w_version: number;
  movie: { id: number; tmdb_id: number | null; title: string; year?: number; overview?: string; trailer_key: string | null };
}

// Onboarding uses the app's own screens; only the header and the trailer/vote loop are training's.
function Top() {
  return (
    <header className="ps-top">
      <a href="/" aria-label="Filmocracy home"><Wordmark /></a>
      <span className="training-label">Taste training</span>
    </header>
  );
}

export function Training() {
  const [step, setStep] = useState<Step>('loading');
  const [name, setName] = useState('');
  const [feeling, setFeeling] = useState<FeelingId | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [feed, setFeed] = useState<string | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [readError, setReadError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [rec, setRec] = useState<Recommendation | null>(null);
  // Films without a stored trailer get theirs from TMDB live, by tmdb_id.
  const trailer = useTrailer(rec?.movie.tmdb_id ?? null, rec?.movie.trailer_key ?? null);
  const [votes, setVotes] = useState(0);
  const [saved, setSaved] = useState(false);
  const [seen, setSeen] = useState<boolean | null>(null);
  const ballotTitle = useRef<HTMLHeadingElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [training, setTraining] = useState<boolean | null>(null);
  const previewUrls = useRef<string[]>([]);
  const scope = useRef<HTMLElement>(null);
  const inflight = useRef(false);
  const choice = FEELINGS.find((f) => f.id === feeling);

  useEffect(() => {
    document.title = 'Train Your Taste · Filmocracy';
  }, []);
  // Returning visitors keep their name and latest feed (same profile and feeds as the app), so skip straight to feeling.
  useEffect(() => {
    Promise.all([http<{ display_name: string | null }>('/profiles/me'), http<{ feed_id: string | null; tags?: Record<string, number> }>('/me')])
      .then(([profile, me]) => {
        if (profile.display_name) setName(profile.display_name);
        if (me.feed_id) { setFeed(me.feed_id); setTags(Object.keys(me.tags ?? {}).slice(0, 8)); }
        setStep(profile.display_name ? 'feeling' : 'name');
      })
      .catch(() => setStep('name'));
  }, []);
  useEffect(() => { scope.current?.querySelector('h1')?.focus(); }, [step]);
  useEffect(() => { if (seen !== null) ballotTitle.current?.focus(); }, [seen]);
  useMotion(() => { gsap.from('.ps > *', { y: 14, autoAlpha: 0, stagger: 0.04, duration: 0.5, ease: 'expo.out' }); }, scope, [step]);
  useEffect(() => () => previewUrls.current.forEach((url) => URL.revokeObjectURL(url)), []);
  useEffect(() => {
    if (!files.length && !busy) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [files.length, busy]);
  useEffect(() => {
    http<{ training_enabled: boolean }>('/ready').then((r) => setTraining(r.training_enabled)).catch(() => {});
  }, [step]);

  async function run(work: () => Promise<unknown>) {
    if (inflight.current) return;
    inflight.current = true;
    setBusy(true);
    setError('');
    try { await work(); }
    catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Couldn’t reconnect your browser. Reload this page and try again. Your saved votes remain on the server.');
      } else setError(err instanceof Error ? err.message : 'Couldn’t connect. Try again.');
    } finally { inflight.current = false; setBusy(false); }
  }

  function setShots(nextFiles: File[]) {
    previewUrls.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrls.current = nextFiles.map((f) => URL.createObjectURL(f));
    setPreviews(previewUrls.current);
    setFiles(nextFiles);
  }

  async function next(fid: string) {
    try {
      const result = await http<Recommendation>(`/training/feeds/${fid}/next`, { boost: choice?.boost ?? [] });
      setRec(result);
      setSeen(null);
      setSaved(false);
      setNotice('');
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) { setStep('done'); return false; }
      throw err;
    }
  }

  function addFiles(added: File[]) {
    if (added.some((f) => !['image/jpeg', 'image/png', 'image/webp'].includes(f.type) || f.size > 10 * 1024 * 1024)) {
      setError('Choose JPEG, PNG or WebP screenshots, up to 10 MB each.');
      return;
    }
    if (files.length + added.length > 3) {
      setError('Choose up to 3 screenshots. Remove one before adding another.');
      return;
    }
    setError('');
    setShots([...files, ...added]);
  }

  // Same as the app's reading screen: upload, show the tags for a moment, then move on.
  useEffect(() => {
    if (step !== 'reading') return;
    let live = true;
    let t: ReturnType<typeof setTimeout>;
    const began = Date.now();
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    http<{ feed_id: string; tags: Record<string, number> }>('/training/feeds', form)
      .then((result) => {
        if (!live) return;
        setFeed(result.feed_id);
        setTags(Object.keys(result.tags).slice(0, 8));
        t = setTimeout(() => {
          setShots([]);
          setStep('watch');
          void run(() => next(result.feed_id));
        }, Math.max(READ_MS - (Date.now() - began), 2500));
      })
      .catch(() => live && setReadError(true));
    return () => { live = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per reading attempt
  }, [step, attempt]);

  const err = error && <p className="field-error" role="alert">{error}</p>;

  if (step === 'loading') return <main className="phone training" ref={scope} aria-busy="true" />;
  if (step === 'name') return <main className="phone training" ref={scope}>
    <NameStep top={<Top />} sub="No account needed. Pick a name, choose a feeling, and share 1–3 Explore screenshots. Then watch trailers and vote." cta="Continue" busy={busy} error={error} onSubmit={(n) => void run(async () => {
      await http('/profiles/me', { display_name: n });
      setName(n);
      setStep('feeling');
    })} />
  </main>;
  if (step === 'feeling') return <main className="phone training" ref={scope}>
    <FeelingStep top={<Top />} sub={feed ? `Welcome back, ${name}. We’ll use this feeling to shape your trailer picks.` : 'We’ll use this feeling to shape your trailer picks.'} feeling={feeling} onPick={setFeeling}
      onContinue={() => { if (!feed) return setStep('screenshots'); setStep('watch'); void run(() => next(feed)); }} />
  </main>;
  if (step === 'screenshots') return <main className="phone training" ref={scope}>
    <ScreenshotsStep
      top={<Top />}
      shots={previews}
      accept="image/jpeg,image/png,image/webp"
      onAdd={addFiles}
      onRemove={(i) => setShots(files.filter((_, j) => j !== i))}
      next={<button className="btn btn-primary" onClick={() => { setTags([]); setReadError(false); setStep('reading'); }}>Read my feed <ArrowRight aria-hidden="true" /></button>}
      fineprint="Filmocracy sends these images to Muse Spark to read your taste. The backend stores the resulting taste profile, not the screenshots."
    >{err}</ScreenshotsStep>
  </main>;
  if (step === 'reading') return <main className="phone training" ref={scope}>
    <ReadingStep shots={previews} tags={tags} error={readError} onRetry={() => { setReadError(false); setAttempt((n) => n + 1); }} onRepick={() => setStep('screenshots')} />
  </main>;

  return (
    <main className="phone training" ref={scope}>
      <section className={`ps training-page ${step === 'watch' ? 'training-page--watch' : ''}`}>
        <Top />
        <h1 tabIndex={-1} className="ps-title display">{step === 'watch' ? (rec ? rec.movie.title : 'Your next trailer is waiting.') : 'That’s a wrap. Thank you.'}</h1>
        {step === 'watch' && <div className="training-watch">
          <div className="training-player">
            {rec ? <>
              {trailer ? <iframe
                key={rec.rec_id}
                className="training-trailer"
                title={`${rec.movie.title} trailer`}
                src={`https://www.youtube-nocookie.com/embed/${trailer}?rel=0&playsinline=1`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
              /> : <div className="training-trailer" role="status">Finding the trailer…</div>}
              <p className="training-note">{rec.movie.year ? `${rec.movie.year} · ` : ''}Watch the trailer, then vote below.</p>
              <a className="training-youtube" href={trailer ? `https://www.youtube.com/watch?v=${trailer}` : `https://www.youtube.com/results?search_query=${encodeURIComponent(`${rec.movie.title} ${rec.movie.year ?? ''} trailer`)}`} target="_blank" rel="noreferrer">{trailer ? 'Trailer won’t play? Open on YouTube' : 'No trailer here? Search YouTube'}</a>
            </> : <p className="ps-sub">Your taste profile is saved. Find a trailer when you’re ready.</p>}
          </div>
          <section className="training-ballot" aria-labelledby="training-vote-title">
            <h2 id="training-vote-title" ref={ballotTitle} tabIndex={-1} className="display training-ballot-title">{saved ? 'Vote saved.' : rec ? seen === null ? 'Have you watched this movie?' : seen ? 'Did you like it?' : 'Would you watch it?' : 'Ready for a trailer?'}</h2>
            {rec && <p className="training-note">{typeof rec.score === 'number' && Number.isFinite(rec.score)
              ? <>AI match score: <strong>{rec.score.toFixed(3)}</strong>. Higher means a stronger predicted match; this is not a confidence percentage.</>
              : 'AI match score unavailable.'}</p>}
            <p className="training-note" role="status">{votes} {votes === 1 ? 'vote' : 'votes'} saved · {notice || 'Your vote stays private.'}</p>
            {rec && !saved ? seen === null ? <div className="training-votes">
              <button className="vote-btn" disabled={busy} onClick={() => setSeen(true)}><Check aria-hidden="true" /><span>Watched</span></button>
              <button className="vote-btn" disabled={busy} onClick={() => setSeen(false)}><X aria-hidden="true" /><span>Not watched</span></button>
            </div> : <>
              <p className="training-note">{seen ? 'Watched' : 'Not watched'} · <button className="training-change" disabled={busy} onClick={() => { setSeen(null); ballotTitle.current?.focus(); }}>Change</button></p>
              <div className="training-votes">
                {([false, true] as const).map((positive) => <button
                  key={String(positive)}
                  className={`vote-btn ${positive ? 'vote-btn--yes' : 'vote-btn--no'}`}
                  disabled={busy}
                  aria-busy={busy}
                  onClick={() => void run(async () => {
                    const label = seen ? positive ? 'seen_loved' : 'seen_disliked' : positive ? 'love' : 'nah';
                    await http('/feedback', { rec_id: rec.rec_id, label });
                    setSaved(true); setVotes((n) => n + 1); setNotice('Vote saved');
                  })}
                >{positive ? <ThumbsUp aria-hidden="true" /> : <ThumbsDown aria-hidden="true" />}<span>{seen ? positive ? 'Liked it' : 'Disliked it' : positive ? 'Interested' : 'Not interested'}</span></button>)}
              </div>
            </> : <button className="btn btn-primary" disabled={busy || !feed} onClick={() => void run(() => next(feed!))}>{busy ? 'Finding a trailer…' : 'Next Trailer'}<ArrowRight aria-hidden="true" /></button>}
            <div className="training-secondary">
              {rec && !saved && <button className="btn btn-ghost" disabled={busy} onClick={() => void run(() => next(feed!))}>Skip trailer</button>}
              <button className="btn btn-ghost" disabled={busy} onClick={() => setStep('done')}>Finish for now</button>
            </div>
          </section>
          {(rec?.movie.overview || tags.length > 0) && <details className="training-about">
            <summary>About this pick</summary>
            {rec?.movie.overview && <p className="training-note">{rec.movie.overview}</p>}
            {tags.length > 0 && <ul className="tags" aria-label="Your taste tags">{tags.map((tag) => <li key={tag}>{tag}</li>)}</ul>}
          </details>}
        </div>}
        {step === 'done' && <>
          <Check className="training-check" aria-hidden="true" />
          <p className="ps-sub">{votes} {votes === 1 ? 'vote' : 'votes'} saved, {name || 'movie fan'}. Your feedback is ready for Filmocracy’s trainer.</p>
          <div className="ps-foot">{feed && <button className="btn btn-primary" disabled={busy} onClick={() => void run(async () => { if (await next(feed)) setStep('watch'); })}>Watch more trailers <ArrowRight aria-hidden="true" /></button>}<a className="btn btn-ghost" href="/">Back to Filmocracy</a></div>
        </>}
        {busy && <p className="training-note" role="status">Saving or finding your next trailer…</p>}
        {err}
        {training === false && <p className="training-note">Votes are saved. Automatic model training is currently off on this server.</p>}
      </section>
    </main>
  );
}
