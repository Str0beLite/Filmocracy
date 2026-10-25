import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, Check, ImagePlus, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { ApiError, http } from '../api/http';
import { FEELINGS } from '../api/data';
import { FEELING_ICONS } from '../lib/feelings';
import { Wordmark } from '../components/ui';
import './training.css';

type Step = 'name' | 'feeling' | 'screenshots' | 'watch' | 'done';
interface Recommendation {
  rec_id: number;
  score?: number;
  w_version: number;
  movie: { id: number; title: string; year?: number; overview?: string; trailer_key: string };
}

export function Training() {
  const [step, setStep] = useState<Step>('name');
  const [name, setName] = useState('');
  const [feeling, setFeeling] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [feed, setFeed] = useState<string | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [votes, setVotes] = useState(0);
  const [saved, setSaved] = useState(false);
  const [seen, setSeen] = useState<boolean | null>(null);
  const ballotTitle = useRef<HTMLHeadingElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [training, setTraining] = useState<boolean | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const previewUrls = useRef<string[]>([]);
  const title = useRef<HTMLHeadingElement>(null);
  const inflight = useRef(false);
  const choice = FEELINGS.find((f) => f.id === feeling);

  useEffect(() => {
    document.title = 'Train Your Taste · Filmocracy';
  }, []);
  useEffect(() => { title.current?.focus(); }, [step]);
  useEffect(() => { if (seen !== null) ballotTitle.current?.focus(); }, [seen]);
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

  function addFiles(list: FileList | null) {
    if (!list) return;
    const added = [...list];
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

  function submitName(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      await http('/profiles/me', { display_name: name.trim() });
      setStep('feeling');
    });
  }

  const heading = {
    name: 'What do your friends call you?',
    feeling: 'How do you want to feel tonight?',
    screenshots: 'Show us your Explore page.',
    watch: rec ? rec.movie.title : 'Your next trailer is waiting.',
    done: 'That’s a wrap. Thank you.',
  }[step];

  return (
    <main className="phone training">
      <a className="training-skip" href="#training-content">Skip to training</a>
      <section className={`ps training-page ${step === 'watch' ? 'training-page--watch' : ''}`}>
        <header className="ps-top"><a href="/" aria-label="Filmocracy home"><Wordmark /></a><span className="training-label">Taste training</span></header>
        <h1 id="training-content" ref={title} tabIndex={-1} className="ps-title display">{heading}</h1>
        {step === 'name' && <form className="training-form" onSubmit={submitName}>
          <p className="ps-sub">No account needed. Pick a name, choose a feeling, and share 1–3 Explore screenshots. Then watch trailers and vote.</p>
          <label className="field">First name<input className="field-text" name="name" autoComplete="given-name" placeholder="Alex…" value={name} onChange={(e) => setName(e.target.value)} maxLength={20} required /></label>
          <div className="ps-foot"><button className="btn btn-primary" disabled={busy || !name.trim()}>Continue <ArrowRight aria-hidden="true" /></button></div>
        </form>}
        {step === 'feeling' && <>
          <p className="ps-sub">We’ll use this feeling to shape your trailer picks.</p>
          <div className="feeling-grid" role="group" aria-label="Tonight’s feeling">
            {FEELINGS.map((f) => { const Icon = FEELING_ICONS[f.id]; return <button key={f.id} className="feeling" aria-pressed={feeling === f.id} onClick={() => setFeeling(f.id)}><Icon aria-hidden="true" />{f.label}</button>; })}
          </div>
          <div className="ps-foot"><button className="btn btn-primary" disabled={!feeling} onClick={() => setStep('screenshots')}>Continue <ArrowRight aria-hidden="true" /></button></div>
        </>}
        {step === 'screenshots' && <>
          <ol className="howto-shots"><li>Open Instagram and tap the search tab.</li><li>Take a screenshot and add it below.</li><li>Optional: scroll and add up to 2 more for sharper picks.</li></ol>
          <div className="shots">
            {Array.from({ length: 3 }, (_, i) => <div key={i} className={`shot-slot ${files[i] ? 'is-filled' : ''}`}>
              {files[i] ? <><img src={previews[i]} alt={`Explore screenshot ${i + 1}`} width={90} height={160} /><button className="training-remove" disabled={busy} aria-label={`Remove screenshot ${i + 1}`} onClick={() => setShots(files.filter((_, j) => j !== i))}><X aria-hidden="true" /></button></> : <><ImagePlus aria-hidden="true" />{i > 0 && <small>Optional</small>}</>}
            </div>)}
          </div>
          <p className="training-note" role="status">{files.length} of 3 screenshots added. Only 1 is needed. JPEG, PNG or WebP, up to 10 MB each.</p>
          <input ref={input} name="screenshots" className="sr-only" aria-label="Choose Explore screenshots" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy} onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }} />
          <div className="ps-foot">
            {files.length < 3 && <button className={files.length ? 'btn btn-ghost' : 'btn btn-primary'} disabled={busy} onClick={() => input.current?.click()}><ImagePlus aria-hidden="true" />{files.length ? 'Add another (optional)' : 'Add screenshots'}</button>}
            <button className="btn btn-primary" disabled={busy || files.length === 0} onClick={() => void run(async () => {
              const form = new FormData(); files.forEach((file) => form.append('files', file));
              const result = await http<{ feed_id: string; tags: Record<string, number> }>('/training/feeds', form);
              setFeed(result.feed_id); setTags(Object.keys(result.tags).slice(0, 6)); setShots([]); setStep('watch');
              await next(result.feed_id);
            })}>{busy ? 'Reading your Explore pages…' : 'Read My Feed'}<ArrowRight aria-hidden="true" /></button>
            <p className="fineprint">Filmocracy sends these images to Muse Spark to read your taste. The backend stores the resulting taste profile, not the screenshots.</p>
          </div>
        </>}
        {step === 'watch' && <div className="training-watch">
          <div className="training-player">
            {rec ? <>
              <iframe
                key={rec.rec_id}
                className="training-trailer"
                title={`${rec.movie.title} trailer`}
                src={`https://www.youtube-nocookie.com/embed/${rec.movie.trailer_key}?rel=0&playsinline=1`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
              />
              <p className="training-note">{rec.movie.year ? `${rec.movie.year} · ` : ''}Watch the trailer, then vote below.</p>
              <a className="training-youtube" href={`https://www.youtube.com/watch?v=${rec.movie.trailer_key}`} target="_blank" rel="noreferrer">Trailer won’t play? Open on YouTube</a>
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
        {busy && <p className="training-note" role="status">{step === 'screenshots' ? 'Reading your screenshots. This can take a minute; keep this page open.' : 'Saving or finding your next trailer…'}</p>}
        {error && <p className="field-error" role="alert">{error}</p>}
        {training === false && <p className="training-note">Votes are saved. Automatic model training is currently off on this server.</p>}
      </section>
    </main>
  );
}
