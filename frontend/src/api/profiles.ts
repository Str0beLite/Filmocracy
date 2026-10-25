import { token } from './auth';

export interface PhoneProfile { name: string; credential: string }
const KEY = 'tandem.phone.profiles';
export const ACTIVE_PROFILE = 'tandem.phone.active-profile';

export function phoneProfiles(): PhoneProfile[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    return Array.isArray(saved) ? saved.filter((p): p is PhoneProfile => Boolean(p && typeof p.name === 'string' && typeof p.credential === 'string')) : [];
  } catch { return []; }
}

export function rememberProfile(name: string) {
  const credential = token();
  const profiles = phoneProfiles().filter((p) => p.credential !== credential);
  localStorage.setItem(KEY, JSON.stringify([...profiles, { name, credential }]));
  localStorage.setItem(ACTIVE_PROFILE, credential);
}

export function selectProfile(credential?: string) {
  const next = credential ?? `guest-${Array.from(crypto.getRandomValues(new Uint8Array(32)), (b) => b.toString(16).padStart(2, '0')).join('')}`;
  if (credential && !phoneProfiles().some((p) => p.credential === credential)) throw new Error('Choose a saved profile.');
  localStorage.setItem(ACTIVE_PROFILE, next);
  for (const key of ['tandem.phone.session', 'tandem-me', 'tandem-votes', 'tandem.guest.token']) sessionStorage.removeItem(key);
}
