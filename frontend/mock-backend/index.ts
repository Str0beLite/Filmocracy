// A fake Tandem backend that runs inside the Vite dev server, so a real
// movie night works across a TV and phones without the Python service.
//
// One in-memory room. Clients POST actions to /mock-api/<action> and listen
// on /mock-api/events (Server-Sent Events), which pushes a Snapshot after
// every change. The server owns every timer and every vote; snapshots never
// say how anyone voted.
//
// The real session layer (FastAPI + WebSockets, see docs/decisions.md) should
// speak the same snapshot/actions protocol, so the screens don't change.

import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';
import { CATALOG, COLORS, FEED_TAG_POOL, FEELINGS, ROOM, TEST_FRIENDS } from '../src/api/mock';
import { MISS_MS, REACTION_MS, REVEAL_MS, TRAILER_GRACE_MS, TRAILER_MS, VOTE_TIMEOUT_MS, isCheckpoint } from '../src/api/rules';
import type { FeelingId, Person, Rec, Snapshot } from '../src/api/types';

type Vote = 'yes' | 'no';
type Round = { n: number; id: number; yes: number; no: number; unanimous: boolean };

interface State {
  people: (Person & { feed: string[] })[];
  phase: Snapshot['phase'];
  round: number;
  movieId: number | null;
  why: Snapshot['why'];
  trailerStartedAt: number | null;
  trailerMs: number;
  votes: Record<string, Vote>; // private: never sent to clients
  outcome: Snapshot['outcome'];
  history: Round[]; // private: yes/no counts
  shown: number[];
  picks: Snapshot['picks'];
  showingId: number | null;
  reactions: Snapshot['reactions'];
}

const fresh = (): State => ({
  people: [],
  phase: 'lobby',
  round: 0,
  movieId: null,
  why: [],
  trailerStartedAt: null,
  trailerMs: TRAILER_MS,
  votes: {},
  outcome: null,
  history: [],
  shown: [],
  picks: null,
  showingId: null,
  reactions: [],
});

let s = fresh();
let timer: ReturnType<typeof setTimeout> | undefined;
let nextId = 1;

const seated = () => s.people.filter((p) => p.seated);
const byId = (id: string) => s.people.find((p) => p.id === id);
const pick = <T>(list: T[], n: number) => [...list].sort(() => Math.random() - 0.5).slice(0, n);

function schedule(fn: () => void, ms: number) {
  clearTimeout(timer);
  timer = setTimeout(() => {
    fn();
    broadcast();
  }, ms);
}

// ---- Fake recommender: the catalog, re-ranked by tonight ----
// Feelings boost matching tags (like the backend's +0.15 tag boost, scaled
// down); every vote nudges films that share tags with what people liked or
// passed on. Stands in for re-calling POST /groups/{id}/recs after each vote.

function ranked(): Rec[] {
  const boost = new Set(seated().flatMap((p) => FEELINGS.find((f) => f.id === p.feeling)?.boost ?? []));
  const taste = new Map<string, number>();
  for (const r of s.history) {
    const film = CATALOG.find((m) => m.id === r.id)!;
    const lean = (r.yes - r.no) / Math.max(1, r.yes + r.no);
    for (const t of film.tags) taste.set(t, (taste.get(t) ?? 0) + lean);
  }
  const score = (m: Rec) =>
    m.score + 0.03 * m.tags.filter((t) => boost.has(t)).length + 0.02 * m.tags.reduce((a, t) => a + (taste.get(t) ?? 0), 0);
  return [...CATALOG].sort((a, b) => score(b) - score(a));
}

function nextMovie() {
  const unseen = ranked().filter((m) => !s.shown.includes(m.id));
  return (unseen[0] ?? ranked()[0]).id; // run out of films? start repeating
}

// Fake `because_of`: up to two people, each with one of their feed tags.
function whyFor(movieId: number): Snapshot['why'] {
  return pick(seated(), 2).map((p, i) => ({ who: p.id, tag: p.feed[(movieId + i) % p.feed.length] }));
}

// Golden buzzers first, then trailers people liked, then predictions.
function rankPicks(): NonNullable<Snapshot['picks']> {
  const top: { id: number; source: 'buzzer' | 'trailers' | 'predicted' }[] = [];
  const add = (id: number, source: (typeof top)[number]['source']) => {
    if (!top.some((p) => p.id === id)) top.push({ id, source });
  };
  s.history.filter((r) => r.unanimous).forEach((r) => add(r.id, 'buzzer'));
  [...s.history]
    .filter((r) => !r.unanimous && r.yes > 0)
    .sort((a, b) => b.yes / (b.yes + b.no) - a.yes / (a.yes + a.no))
    .forEach((r) => add(r.id, 'trailers'));
  const predicted = ranked().filter((m) => !s.shown.includes(m.id)).map((m) => m.id);
  predicted.forEach((id) => add(id, 'predicted'));
  const chosen = top.slice(0, 3);
  const more = predicted.filter((id) => !chosen.some((p) => p.id === id)).slice(0, 5);
  return { top: chosen, more };
}

// ---- The night ----

function startTrailer() {
  s.round += 1;
  s.movieId = nextMovie();
  s.shown.push(s.movieId);
  s.why = whyFor(s.movieId);
  s.phase = 'trailer';
  s.trailerStartedAt = Date.now();
  s.trailerMs = TRAILER_MS;
  s.votes = {};
  s.outcome = null;
  schedule(openVoting, TRAILER_MS);
}

function openVoting() {
  s.phase = 'vote';
  schedule(reveal, VOTE_TIMEOUT_MS);
}

function reveal() {
  s.phase = 'reveal';
  schedule(result, REVEAL_MS);
}

function result() {
  const voters = seated();
  const yes = voters.filter((p) => s.votes[p.id] === 'yes').length;
  const no = voters.filter((p) => s.votes[p.id] === 'no').length;
  const unanimous = voters.length > 0 && yes === voters.length;
  s.history.push({ n: s.round, id: s.movieId!, yes, no, unanimous });
  s.outcome = unanimous ? 'buzzer' : isCheckpoint(s.round) ? 'checkpoint' : 'miss';
  s.phase = 'result';
  if (s.outcome === 'miss') schedule(startTrailer, MISS_MS);
  else clearTimeout(timer);
}

function seatTestFriends() {
  for (const f of TEST_FRIENDS) {
    if (s.people.some((p) => p.name === f.name)) continue;
    s.people.push({
      id: `test-${f.name.toLowerCase()}`,
      name: f.name,
      feeling: f.feeling,
      color: COLORS[s.people.length % COLORS.length],
      seated: true,
      feed: pick(FEED_TAG_POOL, 6),
    });
  }
}

// Each action returns what the caller needs (or nothing) and may change the
// room; every call is followed by a broadcast.
const actions: Record<string, (body: Record<string, string>) => unknown> = {
  join({ name }) {
    const clean = String(name ?? '').trim().slice(0, 20);
    if (!clean) throw new Error('Name required');
    const person = {
      id: `p${nextId++}`,
      name: clean,
      color: COLORS[s.people.length % COLORS.length],
      feeling: null,
      seated: false,
      feed: [],
    };
    s.people.push(person);
    return { id: person.id };
  },
  feeling({ id, feeling }) {
    const p = byId(id);
    if (p && FEELINGS.some((f) => f.id === feeling)) p.feeling = feeling as FeelingId;
  },
  // Stand-in for POST /feeds: "reads" the screenshots, returns tags.
  feed({ id }) {
    const p = byId(id);
    if (!p) throw new Error('Unknown person');
    p.feed = pick(FEED_TAG_POOL, 6);
    return { tags: p.feed };
  },
  seat({ id }) {
    const p = byId(id);
    if (p) p.seated = true;
  },
  start() {
    if (s.phase === 'lobby' && seated().length) startTrailer();
  },
  // The TV found a real trailer and it started playing: time the night to the
  // video. The TV ends it when the video does; the timer is only a backstop.
  trailerPlaying({ round, ms, at }) {
    if (s.phase !== 'trailer' || Number(round) !== s.round) return;
    s.trailerMs = Number(ms);
    s.trailerStartedAt = Date.now() - Number(at);
    schedule(openVoting, s.trailerMs - Number(at) + TRAILER_GRACE_MS);
  },
  endTrailer({ round }) {
    if (s.phase === 'trailer' && (round === undefined || Number(round) === s.round)) openVoting();
  },
  vote({ id, vote }) {
    if (s.phase !== 'vote' || !byId(id)?.seated || (vote !== 'yes' && vote !== 'no')) return;
    s.votes[id] = vote;
    if (seated().every((p) => s.votes[p.id])) reveal();
  },
  next() {
    if (s.phase === 'result') startTrailer();
  },
  picks() {
    clearTimeout(timer);
    s.picks = rankPicks();
    s.phase = 'picks';
  },
  showing({ id }) {
    s.showingId = Number(id) || s.picks?.top[0]?.id || null;
    s.phase = 'showing';
  },
  react({ id, emoji }) {
    if (!byId(id) || s.phase !== 'trailer') return;
    const now = Date.now();
    s.reactions = [...s.reactions.filter((r) => now - r.at < REACTION_MS), { id: nextId++, who: id, emoji, at: now }];
  },
  // Same people, new night.
  newNight() {
    clearTimeout(timer);
    s = { ...fresh(), people: s.people };
  },
  reset() {
    clearTimeout(timer);
    s = fresh();
  },

  // ---- Dev only: fast-forward and jump straight to a screen ----
  devAdvance() {
    if (s.phase === 'lobby') {
      if (!seated().length) seatTestFriends();
      startTrailer();
    } else if (s.phase === 'trailer') openVoting();
    else if (s.phase === 'vote') {
      for (const p of seated()) s.votes[p.id] ??= 'yes';
      reveal();
    } else if (s.phase === 'reveal') result();
    else if (s.phase === 'result') startTrailer();
  },
  devFill() {
    seatTestFriends();
  },
  devGoto({ screen }) {
    clearTimeout(timer);
    s = { ...fresh(), people: s.people };
    if (screen === 'lobby') return;
    if (!seated().length) seatTestFriends();
    const play = (n: number, vote: (p: Person, i: number) => Vote) => {
      for (let i = 0; i < n; i++) {
        startTrailer();
        seated().forEach((p, j) => (s.votes[p.id] = vote(p, j)));
        result();
      }
    };
    const allYes = () => 'yes' as const;
    const oneNo = (_: Person, j: number) => (j === 0 ? 'no' : 'yes') as Vote;
    if (screen === 'trailer' || screen === 'vote' || screen === 'reveal') startTrailer();
    if (screen === 'vote') {
      openVoting();
      s.votes[seated()[0].id] = 'yes';
    }
    if (screen === 'reveal') {
      seated().forEach((p) => (s.votes[p.id] = 'yes'));
      reveal();
    }
    if (screen === 'buzzer') play(1, allYes);
    if (screen === 'miss') play(1, oneNo);
    if (screen === 'checkpoint') play(5, oneNo);
    if (screen === 'picks' || screen === 'showing') {
      play(1, allYes);
      play(2, oneNo);
      actions.picks({});
    }
    if (screen === 'showing') actions.showing({});
    if (s.outcome === 'miss') clearTimeout(timer); // hold the screen for review
  },
};

// ---- Transport ----

function snapshot(): Snapshot {
  const now = Date.now();
  return {
    serverNow: now,
    code: ROOM.code,
    name: ROOM.name,
    people: s.people.map(({ id, name, color, feeling, seated }) => ({ id, name, color, feeling, seated })),
    phase: s.phase,
    round: s.round,
    movieId: s.movieId,
    why: s.why,
    trailerStartedAt: s.trailerStartedAt,
    trailerMs: s.trailerMs,
    locked: Object.keys(s.votes),
    outcome: s.outcome,
    shown: s.shown,
    picks: s.picks,
    showingId: s.showingId,
    reactions: s.reactions.filter((r) => now - r.at < REACTION_MS),
  };
}

const listeners = new Set<ServerResponse>();

function broadcast() {
  const data = `data: ${JSON.stringify(snapshot())}\n\n`;
  for (const res of listeners) res.write(data);
}

function readBody(req: IncomingMessage): Promise<Record<string, string>> {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (c) => (raw += c));
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        resolve({});
      }
    });
  });
}

export function mockBackend(): Plugin {
  return {
    name: 'tandem-mock-backend',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/mock-api', async (req, res) => {
        const name = (req.url ?? '/').split('?')[0].slice(1);

        if (req.method === 'GET' && name === 'events') {
          res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            Connection: 'keep-alive',
          });
          res.write(`data: ${JSON.stringify(snapshot())}\n\n`);
          listeners.add(res);
          const ping = setInterval(() => res.write(': ping\n\n'), 15000);
          req.on('close', () => {
            clearInterval(ping);
            listeners.delete(res);
          });
          return;
        }

        const action = actions[name];
        if (req.method !== 'POST' || !action) {
          res.statusCode = 404;
          res.end();
          return;
        }
        try {
          const out = action(await readBody(req));
          broadcast();
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify(out ?? { ok: true }));
        } catch (e) {
          res.statusCode = 400;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ error: (e as Error).message }));
        }
      });
    },
  };
}
