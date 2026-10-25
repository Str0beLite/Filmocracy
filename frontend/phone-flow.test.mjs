import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

// Load the real browser modules with Vite's environment replaced for Node.
async function browserModule(path, cache = new Map()) {
  path = resolve(import.meta.dirname, path);
  if (cache.has(path)) return cache.get(path);
  let source = ts.transpileModule(await readFile(path, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText.replaceAll('import.meta.env', '{}');
  const imports = [...source.matchAll(/from ['"](.+?)['"]/g)];
  for (const [, name] of imports) {
    const url = await browserModule(resolve(dirname(path), `${name}.ts`), cache);
    source = source.replaceAll(`'${name}'`, `'${url}'`).replaceAll(`"${name}"`, `"${url}"`);
  }
  const url = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
  cache.set(path, url);
  return url;
}
function storage() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
}

test('saved profiles restore their own credential without retaining room votes', async () => {
  globalThis.localStorage = storage(); globalThis.sessionStorage = storage();
  globalThis.location = { pathname: '/phone/join' };
  const { rememberProfile, selectProfile, phoneProfiles } = await import(await browserModule('src/api/profiles.ts'));
  const first = `guest-${'a'.repeat(64)}`;
  localStorage.setItem('tandem.guest.token', first);
  rememberProfile('Alex');
  selectProfile(); rememberProfile('Sam');
  const second = localStorage.getItem('tandem.phone.active-profile');
  assert.notEqual(first, second);
  sessionStorage.setItem('tandem.phone.session', 'old-room');
  sessionStorage.setItem('tandem-votes', '{"1":"yes"}');
  selectProfile(first);
  assert.equal(localStorage.getItem('tandem.phone.active-profile'), first);
  assert.equal(sessionStorage.getItem('tandem.phone.session'), null);
  assert.equal(sessionStorage.getItem('tandem-votes'), null);
  assert.deepEqual(phoneProfiles().map((p) => p.name), ['Alex', 'Sam']);
  assert.throws(() => selectProfile('unknown'));
});

test('a closed round shows its verdict immediately and advances after two seconds', async () => {
  globalThis.localStorage = storage(); globalThis.sessionStorage = storage();
  globalThis.location = { pathname: '/tv', href: 'http://localhost/tv' };
  let tick; let ws; let now = 100000;
  const originalNow = Date.now, originalInterval = globalThis.setInterval;
  Date.now = () => now;
  globalThis.setInterval = (fn, ms) => { if (ms === 250) tick = fn; return 1; };
  globalThis.WebSocket = class {
    constructor() { ws = this; }
    close() {} send() {}
  };
  globalThis.fetch = async (url) => ({ ok: true, json: async () => url.endsWith('/session-catalog') ? [] : url.endsWith('/sessions') ? { session_id: 'room', invite_token: 'invite' } : {} });
  try {
    const api = await import(await browserModule('src/api/index.ts'));
    const snapshots = [];
    api.connect((s) => snapshots.push(s), () => {});
    await new Promise((done) => setTimeout(done, 10));
    const state = {
      session: { id: 'room', host_user_id: 'tv', status: 'active' }, profiles: [], session_members: [], session_movies: [], votes: [], member_state: [], session_feeds: [], reactions: [],
      server_now: new Date(now).toISOString(),
      stage: { phase: 'trailer', round: 1, roundId: 'first', movieId: 1, shown: [], trailerMs: 12000, trailerStartedAt: now },
      voting_rounds: [{ id: 'first', movie_id: 1, closed_at: null, close_reason: null }],
    };
    ws.onmessage({ data: JSON.stringify({ type: 'state', state }) });
    state.voting_rounds[0].closed_at = new Date(now).toISOString();
    state.voting_rounds[0].close_reason = 'completed';
    state.votes = [{ round_id: 'first', user_id: 'a', value: 1 }];
    state.voting_rounds.push({ id: 'second', movie_id: 2, closed_at: null });
    ws.onmessage({ data: JSON.stringify({ type: 'state', state }) });
    assert.equal(snapshots.at(-1).phase, 'result');
    assert.equal(snapshots.at(-1).outcome, 'buzzer');
    now += 1999; tick(); assert.equal(snapshots.at(-1).phase, 'result');
    now += 1; tick(); assert.equal(snapshots.at(-1).phase, 'trailer');
    assert.equal(snapshots.at(-1).movieId, 2);
  } finally { Date.now = originalNow; globalThis.setInterval = originalInterval; }
});
