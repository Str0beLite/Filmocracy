// The one place screens talk to the backend: the session service
// (backend/sqlite_sessions.py). Each device follows one session over a
// WebSocket and turns its state into a Snapshot; actions are HTTP calls.
//
// The TV is the session's host and runs the night. The backend owns joins,
// rounds and votes; the TV decides what's on screen around them (trailer, vote,
// verdict, picks…) and publishes that as the session's "stage", which every
// phone receives in the same snapshot.

import { device, token } from './auth';
import { API, ApiError, http } from './http';
import { formatRuntime, tmdbDetails } from './tmdb';
import { COLORS, EMOTES, FEELINGS, art } from './data';
import { MISS_MS, TRAILER_GRACE_MS, TRAILER_MS, VOTE_TIMEOUT_MS, isCheckpoint } from './rules';
import type { Movie, Outcome, Phase, PickSource, Reaction, Snapshot } from './types';

export type * from './types';
export * from './rules';
export { EMOTES, FEELINGS };

// ---- Movies: the backend's playable catalog (/session-catalog) ----

interface CatalogRow {
  id: number;
  tmdb_id: number | null;
  title: string;
  year: number | string | null;
  tags: string[];
  overview?: string;
  poster_url?: string;
  runtime_minutes?: number;
  genres?: string[];
  trailer_url?: string;
}

const movies = new Map<number, Movie>();
let catalog: Promise<void> | null = null;


function youtubeId(url?: string) {
  try {
    return url ? new URL(url).searchParams.get('v') : null;
  } catch {
    return null;
  }
}

function toMovie(r: CatalogRow): Movie {
  return {
    id: r.id,
    tmdbId: r.tmdb_id,
    title: r.title,
    year: Number(r.year) || 0,
    tags: r.tags ?? [],
    match: null,
    wildcard: false,
    posterUrl: r.poster_url ?? null,
    trailerKey: youtubeId(r.trailer_url),
    runtime: formatRuntime(r.runtime_minutes),
    genres: r.genres ?? [],
    logline: r.overview ?? '',
    ...art(r.id),
  };
}

function loadCatalog(refresh = false) {
  if (refresh) catalog = null;
  catalog ??= http<CatalogRow[]>('/session-catalog')
    .then((rows) => rows.forEach((r) => movies.set(r.id, toMovie(r))))
    .catch((e) => {
      catalog = null;
      throw e;
    });
  return catalog;
}

export const movie = (id: number): Movie =>
  movies.get(id) ?? toMovie({ id, tmdb_id: null, title: 'Untitled', year: null, tags: [] });

// Backend scores run ~0 (median) to ~0.3 (top); this is a display scale only.
const toMatch = (score: number) => Math.min(99, Math.max(1, Math.round(50 + score * 160)));

// ---- What the backend sends ----

interface BackendState {
  session: { id: string; host_user_id: string; status: 'lobby' | 'active' | 'ended'; revision: number };
  profiles: { id: string; display_name: string | null }[];
  session_members: { user_id: string; joined_at: string; left_at: string | null }[];
  session_movies: { movie_id: number; position: number; shown_at: string | null }[];
  voting_rounds: { id: string; movie_id: number; closed_at: string | null; close_reason: string | null }[];
  votes: { round_id: string; user_id: string; value: number }[];
  stage: Partial<Stage>;
  member_state: { user_id: string; feeling: string | null }[];
  session_feeds: string[];
  reactions: { id: number; user_id: string; emoji: string; created_at: string }[];
  server_now: string;
}

// What the TV publishes. Times are server milliseconds.
interface Stage {
  phase: Phase;
  round: number;
  roundId: string | null;
  movieId: number | null;
  trailerStartedAt: number | null;
  trailerMs: number;
  real: boolean; // a real trailer is playing (it reports its own length)
  pausedAt: number | null;
  votingSince: number | null;
  revealAt: number | null;
  outcome: Outcome | null;
  shown: number[];
  picks: Snapshot['picks'];
  showingId: number | null;
  nextInvite: string | null; // set on the old session when the TV starts a new night
}

const LOBBY: Stage = {
  phase: 'lobby',
  round: 0,
  roundId: null,
  movieId: null,
  trailerStartedAt: null,
  trailerMs: TRAILER_MS,
  real: false,
  pausedAt: null,
  votingSince: null,
  revealAt: null,
  outcome: null,
  shown: [],
  picks: null,
  showingId: null,
  nextInvite: null,
};

// ---- Connection ----

type Listener = { onSnapshot: (s: Snapshot) => void; onStatus: (online: boolean) => void };
const listeners = new Set<Listener>();

const SESSION_KEY = device() === 'tv' ? 'tandem.tv.session' : 'tandem.phone.session';
const sessionStore = () => (device() === 'tv' ? localStorage : sessionStorage);
let sessionId: string | null = sessionStore().getItem(SESSION_KEY);
let invite = ''; // TV: the token behind the QR code
let state: BackendState | null = null;
let stage: Stage = LOBBY; // TV: its own copy, published to the backend
let offset = 0; // server clock minus ours
let socket: WebSocket | null = null;
let retry = 0;
let started = false;
let firstState: (() => void) | null = null;
let myId: string | null = null; // resolved by the backend; never the bearer credential

const serverNow = () => Date.now() + offset;

function setSession(id: string | null) {
  sessionId = id;
  if (id) sessionStore().setItem(SESSION_KEY, id);
  else sessionStore().removeItem(SESSION_KEY);
}

function emit(snap: Snapshot) {
  listeners.forEach((l) => {
    l.onStatus(true);
    l.onSnapshot(snap);
  });
}

const status = (online: boolean) => listeners.forEach((l) => l.onStatus(online));

const PREJOIN: Snapshot = {
  serverNow: 0,
  joined: false,
  ended: false,
  invite: '',
  roundId: null,
  code: '',
  name: 'Movie night',
  people: [],
  phase: 'lobby',
  round: 0,
  movieId: null,
  why: [],
  trailerStartedAt: null,
  trailerMs: TRAILER_MS,
  pausedAt: null,
  locked: [],
  outcome: null,
  shown: [],
  picks: null,
  showingId: null,
  reactions: [],
};

function toSnapshot(st: BackendState, sg: Stage): Snapshot {
  const host = st.session.host_user_id;
  const names = new Map(st.profiles.map((p) => [p.id, p.display_name || 'Guest']));
  const feelings = new Map(st.member_state.map((m) => [m.user_id, m.feeling]));
  const seated = new Set(st.session_feeds);
  const people = st.session_members
    .filter((m) => m.user_id !== host && !m.left_at)
    .sort((a, b) => a.joined_at.localeCompare(b.joined_at))
    .map((m, i) => ({
      id: m.user_id,
      name: names.get(m.user_id) ?? 'Guest',
      color: COLORS[i % COLORS.length],
      feeling: (feelings.get(m.user_id) ?? null) as Snapshot['people'][number]['feeling'],
      seated: seated.has(m.user_id),
    }));
  const reactions: Reaction[] = st.reactions.map((r) => ({
    id: r.id,
    who: r.user_id,
    emoji: r.emoji,
    at: Date.parse(r.created_at),
  }));
  return {
    ...PREJOIN,
    serverNow: Date.parse(st.server_now),
    joined: true,
    ended: st.session.status === 'ended',
    invite,
    roundId: sg.roundId,
    code: st.session.id.slice(0, 4).toUpperCase(),
    people,
    phase: sg.phase,
    round: sg.round,
    movieId: sg.movieId,
    trailerStartedAt: sg.trailerStartedAt,
    trailerMs: sg.trailerMs,
    pausedAt: sg.pausedAt,
    locked: sg.roundId ? [...new Set(st.votes.filter((v) => v.round_id === sg.roundId).map((v) => v.user_id))] : [],
    outcome: sg.outcome,
    shown: sg.shown,
    picks: sg.picks,
    showingId: sg.showingId,
    reactions,
  };
}

// Never show a film before its details are in. If the backend queued one this page hasn't loaded (it was
// redeployed with a bigger catalog), fetch the catalog again. If a queued film has no stored details (title,
// poster, runtime, genres, summary), get them from TMDB first. Then show the newest state.
let latest: BackendState | null = null;
let waiting = false;
const tried = new Set<number>(); // ids we already fetched for, so a film nobody knows can't loop
const DETAILS_WAIT_MS = 4000; // past this, show the state anyway; details fill in when they arrive

async function fillDetails(ids: number[]) {
  await Promise.all(
    ids.map(async (id) => {
      const m = movies.get(id);
      if (!m) return;
      const d = await tmdbDetails(m.tmdbId);
      movies.set(id, {
        ...m,
        title: d.title || m.title, // TMDB's title over MovieLens's "Illusionist, The"
        posterUrl: d.poster,
        trailerKey: d.trailer,
        runtime: d.runtime,
        genres: d.genres,
        logline: d.logline,
      });
    }),
  );
  if (state) emit(toSnapshot(state, stage));
}

function onState(st: BackendState) {
  latest = st;
  if (waiting) return;
  const ids = st.session_movies.map((m) => m.movie_id).filter((id) => !tried.has(id));
  const unknown = ids.filter((id) => !movies.has(id));
  const bare = ids.filter((id) => movies.has(id) && !movies.get(id)!.posterUrl && !movies.get(id)!.logline);
  if (!unknown.length && !bare.length) return applyState(st);
  waiting = true;
  ids.forEach((id) => tried.add(id));
  const ready = unknown.length
    ? ((catalog = null), loadCatalog().catch(() => {}))
    : Promise.race([fillDetails(bare), new Promise((r) => setTimeout(r, DETAILS_WAIT_MS))]);
  void ready.finally(() => {
    waiting = false;
    if (unknown.length) unknown.forEach((id) => tried.delete(id)); // look again now the catalog is in, for details
    onState(latest!);
  });
}

function applyState(st: BackendState) {
  const fresh = state?.session.id !== st.session.id;
  state = st;
  offset = Date.parse(st.server_now) - Date.now();
  retry = 0;
  if (device() === 'tv') {
    if (fresh) stage = { ...LOBBY, ...st.stage };
    direct();
  } else {
    stage = { ...LOBBY, ...st.stage };
    const current = st.voting_rounds.find((round) => round.id === stage.roundId);
    // Closing a vote opens the next backend round before the host chooses to continue.
    if (current?.closed_at && ['trailer', 'vote', 'reveal'].includes(stage.phase) && verdict(current) === 'buzzer') {
      stage = { ...stage, phase: 'result', outcome: 'buzzer' };
    }
    if (stage.nextInvite) void followNewNight(stage.nextInvite);
  }
  emit(toSnapshot(st, stage));
  firstState?.();
  firstState = null;
}

function wsUrl(sid: string) {
  const url = new URL(`${API}/sessions/${encodeURIComponent(sid)}/ws`, location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.href;
}

function openSocket() {
  const sid = sessionId;
  const t = token();
  if (!sid || !t) return;
  socket?.close();
  const ws = new WebSocket(wsUrl(sid));
  socket = ws;
  let beat: ReturnType<typeof setInterval> | undefined;
  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'auth', token: t }));
    beat = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: 'heartbeat' })), 10000);
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'state' && sessionId === sid) onState(msg.state);
  };
  ws.onclose = (e) => {
    clearInterval(beat);
    if (socket !== ws) return; // replaced on purpose
    socket = null;
    status(false);
    if (e.code === 4403) {
      // Not in this session any more (ended for good, or we left).
      setSession(null);
      state = null;
      if (device() === 'tv') void startTv();
      else emit(PREJOIN);
      return;
    }
    retry = Math.min(retry + 1, 6);
    setTimeout(openSocket, 500 * 2 ** (retry - 1));
  };
}

// Opens the socket and resolves once the first snapshot of `sid` arrives.
function follow(sid: string) {
  setSession(sid);
  state = null;
  return new Promise<void>((resolve) => {
    firstState = resolve;
    openSocket();
  });
}

async function startTv() {
  await loadCatalog();
  if (sessionId) {
    try {
      const st = await http<BackendState>(`/sessions/${sessionId}`);
      const me = (await http<{ user: string }>('/me')).user;
      if (st.session.host_user_id === me && st.session.status !== 'ended') {
        invite = (await http<{ invite_token: string }>(`/sessions/${sessionId}/invitation`, {})).invite_token;
        return follow(sessionId);
      }
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 404) throw e;
    }
  }
  const made = await http<{ session_id: string; invite_token: string }>('/sessions', { display_name: 'TV' });
  invite = made.invite_token;
  return follow(made.session_id);
}

async function startPhone() {
  if (!sessionId || !token()) return emit(PREJOIN);
  try {
    await http<BackendState>(`/sessions/${sessionId}`);
  } catch (err) {
    if (!(err instanceof ApiError) || ![403, 404].includes(err.status)) throw err;
    setSession(null);
    return emit(PREJOIN);
  }
  await loadCatalog();
  myId = (await http<{ user: string }>('/me')).user;
  await follow(sessionId);
}

async function start() {
  if (started) return;
  started = true;
  try {
    if (device() === 'tv') await startTv();
    else await startPhone();
  } catch {
    started = false;
    status(false);
    setTimeout(start, 3000);
  }
}

// Live room updates. Reconnects on its own when a phone wakes up or the Wi-Fi blips.
export function connect(onSnapshot: (s: Snapshot) => void, onStatus: (online: boolean) => void) {
  const l = { onSnapshot, onStatus };
  listeners.add(l);
  if (state) onSnapshot(toSnapshot(state, stage));
  else if (device() === 'phone' && !sessionId) onSnapshot(PREJOIN);
  void start();
  return () => void listeners.delete(l);
}

// Call after signing in, so a TV waiting for Google can start its room.
export function restart() {
  started = false;
  void start();
}

// ---- The TV runs the night ----

let busy = false; // one backend call at a time from the director
let skipping: string | null = null;

function publish(next: Stage) {
  stage = next;
  if (state) emit(toSnapshot(state, stage));
  if (sessionId) http(`/sessions/${sessionId}/stage`, { stage }).catch(() => {});
}

function trailerFor(round: { id: string; movie_id: number }): Stage {
  return {
    ...stage,
    phase: 'trailer',
    round: stage.round + 1,
    roundId: round.id,
    movieId: round.movie_id,
    trailerStartedAt: serverNow(),
    trailerMs: TRAILER_MS,
    real: false,
    pausedAt: null,
    votingSince: null,
    revealAt: null,
    outcome: null,
  };
}

function verdict(round: { id: string; close_reason: string | null }): Outcome {
  const votes = state!.votes.filter((v) => v.round_id === round.id);
  const everyoneIn = round.close_reason === 'completed' && votes.length > 0 && votes.every((v) => v.value === 1);
  return everyoneIn ? 'buzzer' : isCheckpoint(stage.round) ? 'checkpoint' : 'miss';
}

const openRound = () => state?.voting_rounds.find((r) => !r.closed_at && r.id !== stage.roundId);

function direct() {
  if (!state || busy) return;
  const now = serverNow();
  const current = stage.roundId ? state.voting_rounds.find((r) => r.id === stage.roundId) : undefined;
  if (current?.closed_at && (stage.phase === 'trailer' || stage.phase === 'vote')) {
    publish({ ...stage, phase: 'result', revealAt: now, outcome: verdict(current), shown: [...stage.shown, current.movie_id] });
    return;
  }
  switch (stage.phase) {
    case 'lobby': {
      const open = openRound();
      if (open) publish(trailerFor(open));
      break;
    }
    case 'trailer':
      if (!stage.pausedAt && now >= stage.trailerStartedAt! + stage.trailerMs + (stage.real ? TRAILER_GRACE_MS : 0)) {
        publish({ ...stage, phase: 'vote', votingSince: now });
      }
      break;
    case 'vote':
      // A phone that fell asleep can't stall the night: close the round as it stands.
      if (now >= stage.votingSince! + VOTE_TIMEOUT_MS && skipping !== stage.roundId) {
        skipping = stage.roundId;
        http(`/sessions/${sessionId}/control`, { action: 'skip', expected_round_id: stage.roundId }).catch(() => {});
      }
      break;
    case 'reveal':
      publish({ ...stage, phase: 'result', revealAt: now });
      break;
    case 'result':
      if (stage.outcome === 'miss' && now >= stage.revealAt! + MISS_MS) void next();
      break;
  }
}

if (device() === 'tv') setInterval(direct, 250);

// On to the next trailer: the backend usually opened it already; otherwise
// queue more recommendations, and if there are none left, show the picks.
async function next() {
  if (busy) return;
  const open = openRound();
  if (open) {
    // The backend opened this one when voting closed; re-pick the rest with the votes so far.
    http(`/sessions/${sessionId}/queue`, {}).catch(() => {});
    return publish(trailerFor(open));
  }
  busy = true;
  try {
    const queued = state!.session_movies.some((m) => !m.shown_at);
    if (!queued) await http(`/sessions/${sessionId}/queue`, {});
    await loadCatalog(true);
    const { round_id } = await http<{ round_id: string | null }>(`/sessions/${sessionId}/control`, { action: 'start' });
    if (!round_id) throw new Error('Nothing left to show');
    await waitFor(() => state!.voting_rounds.some((r) => r.id === round_id));
    publish(trailerFor(state!.voting_rounds.find((r) => r.id === round_id)!));
  } catch {
    await picks();
  } finally {
    busy = false;
  }
}

function waitFor(ready: () => boolean, ms = 8000) {
  return new Promise<void>((resolve, reject) => {
    const t0 = Date.now();
    const tick = () => (ready() ? resolve() : Date.now() - t0 > ms ? reject(new Error('timed out')) : setTimeout(tick, 100));
    tick();
  });
}

// Top 3 + 5 more, from the backend's final ranking of tonight's votes, topped
// up with recommendations nobody got to.
async function picks() {
  const ranked = await http<{ movie_id: number; unanimous: boolean; likes: number; predicted_score: number }[]>(
    `/sessions/${sessionId}/rankings`,
  );
  for (const r of ranked) {
    const m = movies.get(r.movie_id);
    if (m) m.match = toMatch(r.predicted_score);
  }
  const source = (r: (typeof ranked)[number]): PickSource['source'] =>
    r.unanimous ? 'buzzer' : r.likes > 0 ? 'trailers' : 'predicted';
  // Includes a trailer the backend had opened but the TV never played.
  const cut = new Set(state!.voting_rounds.filter((r) => r.close_reason === 'ended').map((r) => r.movie_id));
  const unshown = state!.session_movies
    .filter((m) => !m.shown_at || cut.has(m.movie_id))
    .sort((a, b) => a.position - b.position)
    .map((m) => ({ id: m.movie_id, source: 'predicted' as const }));
  const all = [...ranked.map((r) => ({ id: r.movie_id, source: source(r) })), ...unshown];
  const top = all.slice(0, 3);
  const more = all.slice(3, 8).map((p) => p.id);
  await http(`/sessions/${sessionId}/control`, { action: 'end' }).catch(() => {});
  publish({ ...stage, phase: 'picks', roundId: null, picks: { top, more } });
}

async function newNight() {
  const made = await http<{ session_id: string; invite_token: string }>('/sessions', { display_name: 'TV' });
  publish({ ...stage, nextInvite: made.invite_token }); // phones in tonight's room follow along
  invite = made.invite_token;
  await follow(made.session_id);
}

// Phone: the TV started a new night; join it under the same name.
let following: string | null = null;
async function followNewNight(nextInvite: string) {
  if (following === nextInvite || !state) return;
  following = nextInvite;
  const me = state.profiles.find((p) => p.id === myId)?.display_name ?? 'Guest';
  const { session_id } = await http<{ session_id: string }>('/sessions/join', {
    display_name: me,
    invite_token: nextInvite,
  });
  await follow(session_id);
}

// ---- Actions ----

let pendingFeed: string | null = null;

export async function act<T = unknown>(action: string, body: Record<string, unknown> = {}): Promise<T> {
  return (await run(action, body, sessionId)) as T;
}

async function run(action: string, body: Record<string, unknown>, sid: string | null): Promise<unknown> {
  switch (action) {
    // Phone
    case 'join': {
      const inv = sessionStorage.getItem('tandem.phone.invite');
      if (!inv) throw new Error('Scan the QR code on the big screen first');
      await loadCatalog();
      const { session_id } = await http<{ session_id: string }>('/sessions/join', {
        display_name: String(body.name).trim().slice(0, 60),
        invite_token: inv,
      });
      await follow(session_id);
      myId = (await http<{ user: string }>('/me')).user;
      return { id: myId };
    }
    case 'feeling':
      return http(`/sessions/${sid}/feeling`, { feeling: body.feeling });
    case 'feed': {
      const form = new FormData();
      const shots = (body.shots as string[]) ?? [];
      const blobs = await Promise.all(shots.map((u) => fetch(u).then((r) => r.blob())));
      blobs.forEach((b, i) => form.append('files', b, `explore-${i + 1}.png`));
      const feed = await http<{ feed_id: string; tags: Record<string, number> }>('/feeds', form);
      pendingFeed = feed.feed_id;
      return { tags: Object.keys(feed.tags).slice(0, 8) };
    }
    case 'seat': {
      const feedId = body.feedId ?? pendingFeed;
      if (!feedId) throw new Error('Add screenshots before taking your seat.');
      return http(`/sessions/${sid}/feed`, { feed_id: feedId }).catch((e) => {
        if (!(e instanceof ApiError) || e.status !== 409) throw e; // already seated with an earlier feed
      });
    }
    case 'vote':
      return http(`/sessions/${sid}/votes`, { round_id: stage.roundId, value: body.vote === 'yes' ? 1 : -1 });
    case 'react':
      return http(`/sessions/${sid}/react`, { emoji: body.emoji });
    case 'leave': {
      if (sid) await http(`/sessions/${sid}/leave`, {}).catch(() => {});
      const oldSocket = socket;
      socket = null;
      oldSocket?.close();
      setSession(null);
      state = null;
      emit(PREJOIN);
      return null;
    }

    // TV
    case 'start':
      if (!state!.session_movies.some((m) => !m.shown_at)) await http(`/sessions/${sid}/queue`, {});
      await loadCatalog(true);
      return http(`/sessions/${sid}/control`, { action: 'start' });
    case 'trailerPlaying':
      if (stage.phase === 'trailer' && body.round === stage.round) {
        publish({ ...stage, trailerStartedAt: serverNow() - Number(body.at), trailerMs: Number(body.ms), real: true });
      }
      return null;
    case 'pauseTrailer':
      if (stage.phase === 'trailer' && !stage.pausedAt) publish({ ...stage, pausedAt: serverNow() });
      return null;
    case 'resumeTrailer':
      if (stage.pausedAt) {
        publish({ ...stage, trailerStartedAt: stage.trailerStartedAt! + serverNow() - stage.pausedAt, pausedAt: null });
      }
      return null;
    case 'endTrailer':
      if (stage.phase === 'trailer' && (body.round === undefined || body.round === stage.round)) {
        publish({ ...stage, phase: 'vote', pausedAt: null, votingSince: serverNow() });
      }
      return null;
    case 'next':
      return next();
    case 'picks':
      return picks();
    case 'showing':
      publish({ ...stage, phase: 'showing', showingId: Number(body.id) });
      return null;
    case 'newNight':
      return newNight();
    case 'end': {
      // Ends tonight for every phone, then opens a fresh lobby with a new QR code.
      await http(`/sessions/${sid}/control`, { action: 'end' });
      const made = await http<{ session_id: string; invite_token: string }>('/sessions', { display_name: 'TV' });
      invite = made.invite_token;
      return follow(made.session_id);
    }
    case 'devAdvance':
      // Dev fast-forward: trailer -> vote -> close the round as it stands -> next.
      if (stage.phase === 'trailer') return run('endTrailer', {}, sid);
      if (stage.phase === 'vote') {
        return http(`/sessions/${sid}/control`, { action: 'skip', expected_round_id: stage.roundId });
      }
      if (stage.phase === 'result') return next();
      return null;
    default:
      throw new Error(`Unknown action: ${action}`);
  }
}
