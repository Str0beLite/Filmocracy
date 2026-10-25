// Who this device is to the backend: a random user id made up on first visit,
// kept in the browser and sent as the bearer token on every request.
// - VITE_DEV_AUTH=1: each phone tab is its own person (handy for testing a
//   whole group from one laptop). Otherwise a phone keeps its id across visits.
// - The TV always keeps one id per browser so a refresh can still host its room.

export const DEV_AUTH = import.meta.env.VITE_DEV_AUTH === '1';

export const device = (): 'tv' | 'phone' => (location.pathname.startsWith('/phone') ? 'phone' : 'tv');

export function userId(): string {
  const d = device();
  const store = d === 'phone' && DEV_AUTH ? sessionStorage : localStorage;
  const key = `tandem.device-user.${d}`;
  let id = store.getItem(key);
  if (!id) {
    // Not crypto.randomUUID: phones open the laptop over plain http (not a
    // secure context), where it's undefined and the whole app goes blank.
    // Long, because knowing an id is all it takes to act as that user.
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    id = `${d}-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
    store.setItem(key, id);
  }
  return id;
}
