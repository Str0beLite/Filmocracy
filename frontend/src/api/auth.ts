// Keep main's existing browser IDs and the trainer's already-issued guest keys.
// New guest keys map to separate public IDs on the backend. Never use a public
// profile ID as a bearer credential. DEV_AUTH controls per-tab storage only.
export const DEV_AUTH = import.meta.env.VITE_DEV_AUTH === '1';
export const device = (): 'tv' | 'phone' =>
  (location.pathname.startsWith('/phone') || location.pathname.startsWith('/training') ? 'phone' : 'tv');

export function token(): string {
  const d = device();
  const store = d === 'phone' && DEV_AUTH ? sessionStorage : localStorage;
  const legacy = store.getItem(`tandem.device-user.${d}`);
  if (legacy && new RegExp(`^${d}-[a-f0-9]{32}$`).test(legacy)) return legacy;
  // Preserve training visitors from before the main merge, without changing their identity.
  const saved = d === 'phone' ? sessionStorage.getItem('tandem.guest.token') : null;
  const earlier = saved && /^guest-[a-f0-9]{64}$/.test(saved) ? saved : null;
  const key = d === 'tv' ? 'tandem.device-user.tv' : 'tandem.guest.token';
  let value = earlier ?? store.getItem(key);
  if (!value || !/^guest-[a-f0-9]{64}$/.test(value)) {
    const bytes = crypto.getRandomValues(new Uint8Array(d === 'tv' ? 16 : 32));
    value = `${d === 'tv' ? 'tv' : 'guest'}-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
  }
  store.setItem(key, value);
  return value;
}

// Log out: this phone gets a fresh id next time. There's no password, so the old account is gone from here.
export function forget() {
  for (const key of ['tandem.guest.token', 'tandem.device-user.phone']) localStorage.removeItem(key);
  for (const key of ['tandem.guest.token', 'tandem.device-user.phone', 'tandem-me', 'tandem-votes', 'tandem.phone.invite']) {
    sessionStorage.removeItem(key);
  }
}
