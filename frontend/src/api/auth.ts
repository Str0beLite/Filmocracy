// Who this device is to the backend. Every request carries a bearer token:
// - Dev (VITE_DEV_AUTH=1, backend TANDEM_DEV_AUTH=1): the token is a made-up
//   id, so each browser tab (phone) or browser (TV) is its own person.
// - Otherwise: a Google ID token from Google Identity Services. It lives in
//   memory only and lasts about an hour; signing in again refreshes it.

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
export const DEV_AUTH = import.meta.env.VITE_DEV_AUTH === '1';

let googleToken: string | null = null;

function devId(device: 'tv' | 'phone') {
  // The TV keeps one identity per browser so a refresh can still host its room;
  // each phone tab is a new person, like the old fake backend.
  const store = device === 'tv' ? localStorage : sessionStorage;
  const key = `tandem.device-user.${device}`;
  let id = store.getItem(key);
  if (!id) {
    // Not crypto.randomUUID: phones open the laptop over plain http (not a
    // secure context), where it's undefined and the whole app goes blank.
    // The TV's id doubles as its host key (no Google on the big screen), so it's long.
    const bytes = crypto.getRandomValues(new Uint8Array(device === 'tv' ? 16 : 4));
    id = `${device}-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
    store.setItem(key, id);
  }
  return id;
}

export const device = (): 'tv' | 'phone' => (location.pathname.startsWith('/phone') ? 'phone' : 'tv');

export function token(): string | null {
  if (DEV_AUTH || device() === 'tv') return devId(device());
  return googleToken;
}

export const signedIn = () => token() !== null;

// The user id the backend will see for this device (dev only; with Google it's
// the token's `sub`, which /me returns).
export function devUser(): string | null {
  return DEV_AUTH ? devId(device()) : null;
}

// ---- Google Identity Services ----

type Credential = { credential: string };
interface Gis {
  initialize(o: { client_id: string; callback: (r: Credential) => void; auto_select?: boolean }): void;
  renderButton(el: HTMLElement, o: Record<string, unknown>): void;
  prompt(): void;
}
declare global {
  interface Window {
    google?: { accounts: { id: Gis } };
  }
}

let gis: Promise<Gis> | null = null;
function loadGis(): Promise<Gis> {
  gis ??= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://accounts.google.com/gsi/client';
    s.async = true;
    s.onload = () => (window.google ? resolve(window.google.accounts.id) : reject(new Error('Google sign-in failed to load')));
    s.onerror = () => reject(new Error('Google sign-in failed to load'));
    document.head.append(s);
  });
  return gis;
}

const listeners = new Set<() => void>();
export function onSignIn(fn: () => void) {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}

// The given name inside a Google ID token, to prefill "what do your friends call you".
export function googleName(): string {
  if (!googleToken) return '';
  try {
    const payload = JSON.parse(atob(googleToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload.given_name ?? payload.name ?? '';
  } catch {
    return '';
  }
}

// Renders Google's own button into `el`. Resolves once it's on screen.
export async function renderGoogleButton(el: HTMLElement) {
  if (!CLIENT_ID) throw new Error('VITE_GOOGLE_CLIENT_ID is not set');
  const id = await loadGis();
  // Google wants initialize() and prompt() once per page; screens can mount twice.
  if (!initialized) {
    initialized = true;
    id.initialize({
      client_id: CLIENT_ID,
      auto_select: true,
      callback: ({ credential }) => {
        googleToken = credential;
        listeners.forEach((fn) => fn());
      },
    });
    id.prompt();
  }
  id.renderButton(el, { theme: 'filled_black', size: 'large', shape: 'pill', text: 'signin_with', width: 320 });
}
let initialized = false;
