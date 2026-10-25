// Your account on this phone: the feed Filmocracy reads your taste from,
// favourite films, logging out and deleting everything. Lives outside the
// room's flow, so the big screen never pulls you off it.

import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { ArrowLeft, ArrowRight, Plus, Trash2, X } from 'lucide-react';
import { act } from '../api';
import { ApiError, http } from '../api/http';
import { forget } from '../api/auth';
import { Wordmark } from '../components/ui';
import { MAX_SHOTS, READ_MS, ReadingStep, ScreenshotsStep } from './onboarding';

interface Film {
  id: number;
  title: string;
  year: number | null;
}

type Me = { feed_id: string | null; tags?: Record<string, number> };

function Top({ onBack }: { onBack?: () => void }) {
  return (
    <header className="ps-top">
      {onBack ? (
        <button className="back-link" onClick={onBack}>
          <ArrowLeft aria-hidden="true" /> Account
        </button>
      ) : (
        <Link className="back-link" to="/phone">
          <ArrowLeft aria-hidden="true" /> Back
        </Link>
      )}
      <Wordmark />
    </header>
  );
}

const label = (f: Film) => (f.year ? `${f.title} (${f.year})` : f.title);

// Logging out or deleting drops this phone's id and every bit of state built on it.
async function leave() {
  await act('leave').catch(() => {});
  forget();
  location.assign('/phone/join');
}

export function PhoneAccount() {
  const [me, setMe] = useState<Me | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [favs, setFavs] = useState<Film[]>([]);
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<Film[]>([]);
  const [error, setError] = useState('');
  const [mode, setMode] = useState<'home' | 'shots' | 'reading'>('home');
  const [files, setFiles] = useState<File[]>([]);
  const [shots, setShots] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [readError, setReadError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const load = () =>
    Promise.all([http<Me>('/me'), http<{ display_name: string | null }>('/profiles/me'), http<Film[]>('/me/favourites')])
      .then(([m, p, f]) => {
        setMe(m);
        setName(p.display_name);
        setFavs(f);
      })
      .catch(() => setError('Couldn’t load your account. Check your connection, then reload.'));

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const q = query.trim();
    if (!q) return;
    const t = setTimeout(() => {
      http<Film[]>(`/movies/search?q=${encodeURIComponent(q)}&limit=6`).then(setFound).catch(() => setFound([]));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  // Same pacing as onboarding: the tags get a moment on screen, then back to the account.
  useEffect(() => {
    if (mode !== 'reading') return;
    let live = true;
    let t: ReturnType<typeof setTimeout>;
    const began = Date.now();
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    http<{ tags: Record<string, number> }>('/feeds', form)
      .then((r) => {
        if (!live) return;
        setTags(Object.keys(r.tags).slice(0, 8));
        t = setTimeout(() => {
          setMode('home');
          setFiles([]);
          setShots([]);
          setTags([]);
          load();
        }, Math.max(READ_MS - (Date.now() - began), 2500));
      })
      .catch(() => live && setReadError(true));
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [mode, files, attempt]);

  const add = async (film: Film) => {
    setError('');
    try {
      await http('/me/favourites', { movie_ids: [film.id] });
      setFavs([film, ...favs.filter((f) => f.id !== film.id)]);
      setQuery('');
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? 'Add your Explore page first.' : 'Couldn’t save that film. Try again.');
    }
  };

  const remove = async (film: Film) => {
    setError('');
    try {
      await http(`/me/favourites/${film.id}`, undefined, 'DELETE');
      setFavs(favs.filter((f) => f.id !== film.id));
    } catch {
      setError('Couldn’t remove that film. Try again.');
    }
  };

  if (mode === 'shots') {
    return (
      <main className="phone">
        <ScreenshotsStep
          top={<Top onBack={() => setMode('home')} />}
          shots={shots}
          onAdd={(picked) => {
            setFiles([...files, ...picked].slice(-MAX_SHOTS));
            setShots([...shots, ...picked.map((f) => URL.createObjectURL(f))].slice(-MAX_SHOTS));
          }}
          onRemove={(i) => {
            setFiles(files.filter((_, j) => j !== i));
            setShots(shots.filter((_, j) => j !== i));
          }}
          next={
            <button className="btn btn-primary" onClick={() => setMode('reading')}>
              Read my feed <ArrowRight aria-hidden="true" />
            </button>
          }
          fineprint="Your new Explore page replaces the old one for future picks."
        />
      </main>
    );
  }

  if (mode === 'reading') {
    return (
      <main className="phone">
        <ReadingStep
          shots={shots}
          tags={tags}
          error={readError}
          onRetry={() => {
            setReadError(false);
            setAttempt((n) => n + 1);
          }}
          onRepick={() => {
            setReadError(false);
            setMode('shots');
          }}
        />
      </main>
    );
  }

  const feedTags = Object.keys(me?.tags ?? {}).slice(0, 10);
  const favIds = new Set(favs.map((f) => f.id));

  return (
    <main className="phone">
      <section className="ps">
        <Top />
        <h1 className="ps-title display">{name ? `Hi, ${name}.` : 'Your account'}</h1>
        <p className="ps-sub">Filmocracy keeps your taste on this phone. There’s no password.</p>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}

        <h2 className="label">Your Explore page</h2>
        {me?.feed_id ? (
          <ul className="tags tags--left">
            {feedTags.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        ) : (
          <p className="ps-sub">{me ? 'Not added yet.' : 'Loading…'}</p>
        )}
        <button className="btn btn-ghost account-gap" onClick={() => setMode('shots')}>
          {me?.feed_id ? 'Update my Explore page' : 'Add my Explore page'}
        </button>

        <h2 className="label">Favourite films</h2>
        <label className="field">
          Add a film
          <input
            className="field-text"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search titles…"
            autoComplete="off"
            name="film"
            disabled={!me?.feed_id}
          />
        </label>
        {!me?.feed_id && me && <p className="fineprint account-left">Add your Explore page first, then save favourites.</p>}
        {query.trim() !== '' && found.length > 0 && (
          <ul className="film-list" aria-label="Search results">
            {found.map((f) => (
              <li key={f.id}>
                <span>{label(f)}</span>
                <button className="icon-btn" onClick={() => add(f)} disabled={favIds.has(f.id)} aria-label={`Add ${label(f)} to favourites`}>
                  <Plus aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {favs.length > 0 ? (
          <ul className="film-list" aria-label="Your favourites">
            {favs.map((f) => (
              <li key={f.id}>
                <span>{label(f)}</span>
                <button className="icon-btn" onClick={() => remove(f)} aria-label={`Remove ${label(f)} from favourites`}>
                  <X aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          me && <p className="fineprint account-left">No favourites yet.</p>
        )}

        <div className="ps-foot">
          <button
            className="btn btn-ghost"
            onClick={() =>
              confirm('Log out? There’s no password, so this account can’t be opened again on any phone.') && leave()
            }
          >
            Log out
          </button>
          <button
            className="btn btn-danger"
            onClick={async () => {
              if (!confirm('Delete your account? Your Explore page, favourites and votes are erased for good.')) return;
              try {
                await http('/me', undefined, 'DELETE');
                await leave();
              } catch {
                setError('Couldn’t delete your account. Try again.');
              }
            }}
          >
            <Trash2 aria-hidden="true" /> Delete account
          </button>
        </div>
      </section>
    </main>
  );
}
