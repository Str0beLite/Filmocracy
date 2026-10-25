import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, UserPlus } from 'lucide-react';
import { Link } from 'react-router';
import { act } from '../api';
import { token } from '../api/auth';
import { http } from '../api/http';
import { phoneProfiles, rememberProfile, selectProfile, type PhoneProfile } from '../api/profiles';
import { Wordmark } from '../components/ui';
import { ScreenshotsStep } from './onboarding';

export function PhoneSettings() {
  const [name, setName] = useState('');
  const [profiles, setProfiles] = useState<PhoneProfile[]>([]);
  const [feed, setFeed] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [shots, setShots] = useState<string[]>([]);
  const urls = useRef<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let live = true;
    Promise.all([http<{ display_name: string | null }>('/profiles/me'), http<{ feed_id: string | null }>('/me')])
      .then(([profile, me]) => {
        if (!live) return;
        setName(profile.display_name ?? '');
        setFeed(me.feed_id);
        if (profile.display_name) rememberProfile(profile.display_name);
        setProfiles(phoneProfiles());
      })
      .catch(() => { if (live) setError('Couldn’t load your profile. Reload to try again.'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; urls.current.forEach((url) => URL.revokeObjectURL(url)); };
  }, []);

  useEffect(() => {
    if (!editing || (!files.length && !busy)) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [editing, files.length, busy]);

  function choose(next: File[]) {
    urls.current.forEach((url) => URL.revokeObjectURL(url));
    urls.current = next.map((file) => URL.createObjectURL(file));
    setFiles(next);
    setShots(urls.current);
  }

  async function switchTo(credential?: string) {
    setBusy(true);
    setError('');
    try {
      await act('leave');
      selectProfile(credential);
      location.assign(credential ? '/phone/join' : '/phone/name');
    } catch { setError('Couldn’t switch profiles. Try again.'); setBusy(false); }
  }

  const top = <header className="ps-top"><Wordmark /></header>;
  if (editing) return <ScreenshotsStep top={top} shots={shots} accept="image/jpeg,image/png,image/webp"
    onAdd={(added) => {
      if (busy) return;
      if (files.length + added.length > 3 || added.some((file) => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024)) {
        setError('Choose up to 3 JPEG, PNG or WebP screenshots, up to 10 MB each.');
        return;
      }
      setError(''); choose([...files, ...added]);
    }}
    onRemove={busy ? undefined : (i) => choose(files.filter((_, j) => i !== j))}
    next={<button className="btn btn-primary" disabled={busy} onClick={() => {
      setBusy(true); setError('');
      const form = new FormData(); files.forEach((file) => form.append('files', file));
      void http<{ feed_id: string }>('/training/feeds', form).then((result) => {
        setFeed(result.feed_id); choose([]); setEditing(false);
        setNotice('Taste updated. Your new screenshots will shape the next room you join.');
      }).catch((err) => setError(err instanceof Error ? err.message : 'Couldn’t read your screenshots. Try again.'))
        .finally(() => setBusy(false));
    }}>{busy ? 'Reading your screenshots…' : 'Update my taste'} <ArrowRight aria-hidden="true" /></button>}
    fineprint="Screenshots are sent to Muse Spark to read your taste. Your current room keeps the taste you joined with."
  >
    {error && <p className="field-error" role="alert">{error}</p>}
    <button className="btn btn-ghost settings-cancel" disabled={busy} onClick={() => { choose([]); setEditing(false); setError(''); }}>Cancel</button>
  </ScreenshotsStep>;

  return <section className="ps settings-page" aria-busy={loading || busy}>
    {top}
    <h1 className="ps-title display" tabIndex={-1}>Your seat, your taste.</h1>
    <p className="ps-sub">{loading ? 'Loading your profile…' : name ? `You’re using ${name}’s profile.` : 'Create a profile to keep your movie taste on this phone.'}</p>
    {error && <p className="field-error" role="alert">{error}</p>}
    {notice && <p className="settings-notice" role="status">{notice}</p>}
    <section className="settings-section" aria-labelledby="settings-taste">
      <h2 id="settings-taste" className="display">Instagram taste</h2>
      <p className="ps-sub">{feed ? 'Your taste is saved. Refresh it whenever your Explore page changes.' : 'Add 1–3 Explore screenshots to find films that feel like you.'}</p>
      <button className="btn btn-ghost" disabled={loading || busy} onClick={() => { setEditing(true); setError(''); setNotice(''); }}>{feed ? 'Replace screenshots' : 'Add screenshots'}</button>
    </section>
    <section className="settings-section" aria-labelledby="settings-profiles">
      <h2 id="settings-profiles" className="display">Profiles on this phone</h2>
      <p className="fineprint settings-local">Saved on this browser. Each profile keeps its own taste and votes.</p>
      <ul className="settings-profiles">
        {profiles.map((profile) => <li key={profile.credential}>
          <button className="settings-profile" disabled={loading || busy || profile.credential === token()} onClick={() => void switchTo(profile.credential)}>
            <span>{profile.name}</span>{profile.credential === token() ? <><span className="sr-only">Current profile</span><Check aria-hidden="true" /></> : <ArrowRight aria-hidden="true" />}
          </button>
        </li>)}
      </ul>
      <button className="btn btn-ghost" disabled={loading || busy} onClick={() => void switchTo()}><UserPlus aria-hidden="true" />Use another profile</button>
    </section>
    <div className="ps-foot"><Link className="btn btn-ghost" to="/phone/lobby"><ArrowLeft aria-hidden="true" />Back to movie night</Link></div>
  </section>;
}
