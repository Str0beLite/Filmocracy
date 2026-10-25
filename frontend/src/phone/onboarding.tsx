// The onboarding screens: name, feeling, Explore screenshots, reading. The
// phone's movie-night flow and /training both render these; each passes its
// own header and decides what the buttons do.

import { useRef, useState, type ReactNode } from 'react';
import { ArrowRight, ImagePlus, X } from 'lucide-react';
import { FEELINGS, type FeelingId } from '../api';
import { FEELING_ICONS } from '../lib/feelings';
import { useElapsed } from '../lib/motion';

export function NameStep({
  top,
  sub,
  cta,
  busy,
  error,
  onSubmit,
}: {
  top: ReactNode;
  sub: string;
  cta: string;
  busy: boolean;
  error: string;
  onSubmit: (name: string) => void;
}) {
  const [name, setName] = useState('');
  return (
    <section className="ps">
      {top}
      <form
        style={{ display: 'contents' }}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(name.trim());
        }}
      >
        <h1 className="ps-title display" tabIndex={-1}>
          What do your friends call you?
        </h1>
        <p className="ps-sub">{sub}</p>
        <label className="field">
          First name
          <input
            className="field-text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Alex…"
            autoComplete="given-name"
            name="name"
            maxLength={20}
            aria-invalid={Boolean(error)}
          />
        </label>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="ps-foot">
          <button className="btn btn-primary" disabled={!name.trim() || busy}>
            {cta} <ArrowRight aria-hidden="true" />
          </button>
        </div>
      </form>
    </section>
  );
}

export function FeelingStep({
  top,
  sub,
  feeling,
  onPick,
  onContinue,
  busy = false,
  error = '',
}: {
  top: ReactNode;
  sub: string;
  feeling: FeelingId | null;
  onPick: (id: FeelingId) => void;
  onContinue: () => void;
  busy?: boolean;
  error?: string;
}) {
  return (
    <section className="ps">
      {top}
      <h1 className="ps-title display" tabIndex={-1}>
        How do you want to feel tonight?
      </h1>
      <p className="ps-sub">{sub}</p>
      <div className="feeling-grid" role="radiogroup" aria-label="Tonight’s feeling">
        {FEELINGS.map((f) => {
          const Icon = FEELING_ICONS[f.id];
          return (
            <button key={f.id} role="radio" aria-checked={feeling === f.id} className="feeling" disabled={busy} onClick={() => onPick(f.id)}>
              <Icon aria-hidden="true" />
              {f.label}
            </button>
          );
        })}
      </div>
      <div className="ps-foot">
        {error && <p className="field-error" role="alert">{error}</p>}
        <button className="btn btn-primary" disabled={!feeling || busy} onClick={onContinue}>
          Continue <ArrowRight aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

// One Explore screenshot is enough; each extra one (up to 3) steadies the picks,
// since a single page can lean hard one way.
export const MAX_SHOTS = 3;

export function ScreenshotsStep({
  top,
  shots,
  accept = 'image/*',
  onAdd,
  onRemove,
  next,
  fineprint,
  children,
}: {
  top: ReactNode;
  shots: string[]; // preview URLs
  accept?: string;
  onAdd: (files: File[]) => void;
  onRemove?: (index: number) => void;
  next: ReactNode; // the primary button, shown once there's a screenshot
  fineprint: string;
  children?: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const full = shots.length >= MAX_SHOTS;
  const pick = () => input.current?.click();

  return (
    <section className="ps">
      {top}
      <h1 className="ps-title display" tabIndex={-1}>
        Show us your Explore page.
      </h1>
      <ol className="howto-shots">
        <li>Open Instagram and tap the search tab.</li>
        <li>Take a screenshot and add it here.</li>
        <li>Optional: scroll and add up to 2 more for sharper picks.</li>
      </ol>
      <div className="shots">
        {Array.from({ length: MAX_SHOTS }, (_, i) => (
          <div key={i} className={`shot-slot ${shots[i] ? 'is-filled' : ''} ${i === shots.length ? 'is-next' : ''}`}>
            {shots[i] ? (
              <>
                <img src={shots[i]} alt={`Screenshot ${i + 1}`} width={90} height={160} />
                {onRemove && (
                  <button className="shot-remove" aria-label={`Remove screenshot ${i + 1}`} onClick={() => onRemove(i)}>
                    <X aria-hidden="true" />
                  </button>
                )}
              </>
            ) : (
              <>
                <ImagePlus aria-hidden="true" />
                {i > 0 && <small>Optional</small>}
              </>
            )}
          </div>
        ))}
      </div>
      {children}
      <div className="ps-foot">
        <input
          ref={input}
          className="file-input"
          type="file"
          accept={accept}
          multiple
          onChange={(e) => {
            onAdd([...(e.target.files ?? [])]);
            e.target.value = '';
          }}
          tabIndex={-1}
          aria-hidden="true"
        />
        {shots.length ? (
          <>
            {next}
            {!full && (
              <button className="btn btn-ghost" onClick={pick}>
                <ImagePlus aria-hidden="true" />
                Add another for sharper picks
              </button>
            )}
          </>
        ) : (
          <button className="btn btn-primary" onClick={pick}>
            <ImagePlus aria-hidden="true" />
            Add a screenshot
          </button>
        )}
        <p className="fineprint">{fineprint}</p>
      </div>
    </section>
  );
}

// How long the tags get on screen before moving on, counted from when reading began.
export const READ_MS = 5200;

export function ReadingStep({
  shots,
  tags,
  error,
  onRetry,
  onRepick,
}: {
  shots: string[];
  tags: string[];
  error: boolean;
  onRetry: () => void;
  onRepick: () => void;
}) {
  const elapsed = useElapsed(150);
  const shown = tags.filter((_, i) => elapsed > 700 + i * 650);
  const finished = tags.length > 0 && shown.length === tags.length;

  if (error) {
    return (
      <section className="ps ps--center">
        <h1 className="ps-title display" tabIndex={-1}>
          Couldn’t read your feed.
        </h1>
        <p className="ps-sub">Check your connection, then try again. Or pick different screenshots.</p>
        <div className="ps-foot">
          <button className="btn btn-primary" onClick={onRetry}>
            Try again
          </button>
          <button className="btn btn-ghost" onClick={onRepick}>
            Pick other screenshots
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="ps ps--center">
      <div className="reading-shots" aria-hidden="true">
        {shots.map((src) => (
          <div key={src} className="reading-shot">
            <img src={src} alt="" width={74} height={132} />
          </div>
        ))}
      </div>
      <h1 className="ps-title display" tabIndex={-1}>
        {finished ? 'Got your vibe.' : 'Reading your Explore page…'}
      </h1>
      <p className="ps-sub">Filmocracy turns what your feed is full of into movie taste.</p>
      <ul className="tags" aria-live="polite">
        {shown.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      <div className="ps-foot" />
    </section>
  );
}
