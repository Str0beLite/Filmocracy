import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import test from 'node:test';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require = createRequire(import.meta.url);
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
    const url = name.startsWith('.')
      ? await browserModule(resolve(dirname(path), `${name}.ts`), cache)
      : pathToFileURL(require.resolve(name)).href;
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

for (const outcome of ['miss', 'buzzer']) test(`a ${outcome} verdict appears immediately and ${outcome === 'buzzer' ? 'waits for the host' : 'advances after two seconds'}`, async () => {
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
    const api = await import(`${await browserModule('src/api/index.ts')}#${outcome}`);
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
    state.votes = [{ round_id: 'first', user_id: 'a', value: outcome === 'buzzer' ? 1 : -1 }];
    state.voting_rounds.push({ id: 'second', movie_id: 2, closed_at: null });
    ws.onmessage({ data: JSON.stringify({ type: 'state', state }) });
    assert.equal(snapshots.at(-1).phase, 'result');
    assert.equal(snapshots.at(-1).outcome, outcome);
    now += 1999; tick(); assert.equal(snapshots.at(-1).phase, 'result');
    now += 1; tick();
    if (outcome === 'buzzer') {
      assert.equal(snapshots.at(-1).phase, 'result');
      now += 60000; tick();
      assert.equal(snapshots.at(-1).phase, 'result');
      await api.act('next');
    }
    assert.equal(snapshots.at(-1).phase, 'trailer');
    assert.equal(snapshots.at(-1).movieId, 2);
  } finally { Date.now = originalNow; globalThis.setInterval = originalInterval; }
});

test('logout clears the active identity and deletion removes only that saved profile', async () => {
  globalThis.localStorage = storage(); globalThis.sessionStorage = storage();
  globalThis.location = { pathname: '/phone/account' };
  const { forget, token } = await import(await browserModule('src/api/auth.ts'));
  const first = `guest-${'a'.repeat(64)}`, second = `guest-${'b'.repeat(64)}`;
  localStorage.setItem('tandem.phone.profiles', JSON.stringify([{name:'Alex', credential:first}, {name:'Sam',credential:second}]));
  localStorage.setItem('tandem.phone.active-profile', first);
  forget();
  assert.notEqual(token(), first);
  assert.equal(JSON.parse(localStorage.getItem('tandem.phone.profiles')).length, 2);
  localStorage.setItem('tandem.phone.active-profile', first);
  forget(true);
  assert.deepEqual(JSON.parse(localStorage.getItem('tandem.phone.profiles')).map((p) => p.name), ['Sam']);
});

test('phones show the golden buzzer when voting closes and wait for a new host stage', async () => {
  globalThis.localStorage = storage(); globalThis.sessionStorage = storage();
  globalThis.location = { pathname: '/phone/vote/1', href: 'http://localhost/phone/vote/1' };
  sessionStorage.setItem('tandem.phone.session', 'phone-room');
  let ws;
  globalThis.WebSocket = class { constructor() { ws = this; } close() {} send() {} };
  globalThis.fetch = async (url) => ({ ok: true, json: async () => url.endsWith('/session-catalog') ? [] : url.endsWith('/me') ? {user:'a'} : {session:{status:'active'}} });
  const api = await import(`${await browserModule('src/api/index.ts')}#phone-buzzer`);
  const flow = await import(await browserModule('src/lib/flow.ts'));
  const snapshots = [];
  api.connect((s) => snapshots.push(s), () => {});
  await new Promise((done) => setTimeout(done, 10));
  const state = {
    session: {id:'phone-room',host_user_id:'tv',status:'active'}, profiles:[],session_members:[], session_movies:[], member_state:[], session_feeds:[],reactions:[],
    server_now: new Date().toISOString(),
    stage:{phase:'vote',round:1,roundId:'first',movieId:1},
    voting_rounds:[{id:'first',movie_id:1,closed_at:'now',close_reason:'completed'},{id:'second',movie_id:2,closed_at:null}],
    votes:[{round_id:'first',user_id:'a',value:1},{round_id:'first',user_id:'b',value:1}],
  };
  const send = () => ws.onmessage({data:JSON.stringify({type:'state',state})});
  send();
  assert.equal(flow.phonePath(snapshots.at(-1),'a'), '/phone/buzzer/1');
  // Heartbeats and the already-open next round must not release the phone.
  state.server_now = new Date(Date.now()+60000).toISOString();
  state.stage.phase = 'trailer';
  send();
  assert.equal(flow.phonePath(snapshots.at(-1),'a'), '/phone/buzzer/1');
  state.stage = {phase:'trailer',round:2,roundId:'second',movieId:2};
  send();
  assert.equal(flow.phonePath(snapshots.at(-1),'a'), '/phone/react/2');
});
