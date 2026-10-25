# Frontend integration

This guide describes the implemented FastAPI service and Supabase schema. The
recommendation implementation is owned by the algorithm teammate and is unchanged.
Embeddings are deferred. API base: `http://localhost:8000` during development;
replace with the approved HTTPS backend URL when deployed.

## Authentication and identity

Clients need the Supabase URL and **publishable** key, plus the FastAPI base URL.
Never ship the secret/service-role key or TMDB token in frontend code. Each device
has its own Supabase Auth identity. Anonymous sign-ins must be enabled in the
project; guest Auth users still use the `authenticated` Postgres role.

```js
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
});
let { data: { session }, error } = await supabase.auth.getSession();
if (error) throw error;
if (!session) {
  const result = await supabase.auth.signInAnonymously();
  if (result.error) throw result.error;
  session = result.data.session;
}
```

Use one client per browser app. Obtain the current access token before each API
request rather than caching a JWT indefinitely:

```js
async function api(path, { method = 'GET', body } = {}) {
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  if (!data.session) throw new Error('Restore your sign-in before continuing.');
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { Authorization: `Bearer ${data.session.access_token}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(typeof result.detail === 'string'
      ? result.detail : 'Check the submitted fields.');
    error.status = response.status;
    error.detail = result.detail;
    throw error;
  }
  return result;
}
```

FastAPI verifies the token with Supabase Auth, then forwards it to database RPCs
and queries. It derives identity from the JWT, never from a request-body user_id.
Do not send a publishable key as the bearer token. RLS restricts session data to
joined members. Group members can read each other's votes and profile names.

## API endpoints

All successful responses below are HTTP **200**. All endpoints except `/health`
require `Authorization: Bearer <user access token>`. Empty-body POST requests need
no JSON. IDs are UUID strings, movie IDs are integers, and dates are ISO 8601.

| Method / path | JSON request | JSON response | Who |
| --- | --- | --- | --- |
| GET /health | — | `{ "status": "ok" }` | Public; process liveness only |
| POST /sessions | `{ "display_name": "TV" }` | `{ "session_id": "uuid", "invite_token": "64 hex characters" }` | Signed-in device creates a host session |
| POST /sessions/join | `{ "display_name": "Alice", "invite_token": "64 characters" }` | `{ "session_id": "uuid" }` | Signed-in phone with a valid invitation |
| GET /sessions/{session_id} | — | SessionState, below | Joined member |
| POST /sessions/{session_id}/invitation | — | `{ "invite_token": "64 hex characters" }` | Host; rotates and invalidates old invitation |
| POST /sessions/{session_id}/queue | — | `{ "added": 5 }` | Host; appends IDs from existing mock provider |
| POST /sessions/{session_id}/control | `{ "action": "start" }` | `{ "round_id": "uuid or null" }` | Host |
| POST /sessions/{session_id}/control | `{ "action": "skip", "expected_round_id": "uuid" }` | `{ "round_id": "uuid or null" }` | Host; round ID required for skip |
| POST /sessions/{session_id}/control | `{ "action": "end" }` | `{ "round_id": null }` | Host; closes current round and session |
| POST /sessions/{session_id}/votes | `{ "round_id": "uuid", "value": 1 }` | `{ "round_id": "uuid or null" }` | Eligible phone; -1=dislike, +1=like |
| POST /sessions/{session_id}/heartbeat | — | `{ "round_id": "uuid or null" }` | Member; renew every 10 seconds |
| POST /sessions/{session_id}/leave | — | `{ "round_id": "uuid or null" }` | Member; leaves immediately |

`display_name`: 1–60 characters, must not be whitespace-only. `invite_token` must
have length 64; database verifies its hash and expiry. `value` must be -1 or +1.
`expected_round_id` is optional for start/end and required for skip. UUIDs are
validated. A round_id response contains an actual UUID string or JSON null, never
the literal string "uuid or null". Extra request properties are currently ignored;
they never grant authority or change the voting identity.

The machine-readable [OpenAPI specification](openapi.json) includes all request
and response schemas. Live `/openapi.json`, `/docs`, and `/redoc` are available.
Regenerate from the repo root with:

```bash
backend/.venv/bin/python backend/scripts/export_openapi.py
```

### SessionState response

Top-level keys: `session`, `session_members`, `session_movies`, `voting_rounds`,
`round_participants`, `votes`. Arrays may be empty and are **not ordered**; sort
queue/history by position. The exact row fields are:

| Object | Fields |
| --- | --- |
| session | id, host_user_id, status (`lobby`/`active`/`ended`), created_at, expires_at, ended_at (nullable) |
| session_members[] | session_id, user_id, is_voter (boolean), joined_at, last_seen_at, left_at (nullable) |
| session_movies[] | session_id, movie_id, position (positive integer), shown_at (nullable until shown) |
| voting_rounds[] | id, session_id, movie_id, opened_at, closed_at (nullable), close_reason (nullable or `completed`/`skipped`/`ended`) |
| round_participants[] | session_id, round_id, user_id, excluded_at (nullable) |
| votes[] | session_id, round_id, user_id, value (-1/+1), created_at, updated_at |

The current round is the one row whose closed_at is null. No current round means
lobby/queue exhausted or ended; inspect session.status. Match its movie_id to
session_movies and retrieve movie metadata from Supabase. GET currently performs
several database reads; it is a converging snapshot, not a transactionally
consistent read across all arrays. Refetch on change notifications, after mutation
responses, and on reconnect; do not compute authoritative completion in the UI.

### Movie metadata and names

FastAPI has no movie metadata or profile-list endpoint. Use Supabase reads with
the browser's user JWT and publishable key:

```js
const movies = await supabase.from('movies').select('*').in('id', movieIds);
const profiles = await supabase.from('profiles')
  .select('id,display_name').in('id', memberUserIds);
```

Movies contain id, provider, provider_movie_id, title, overview, poster_url,
release_date, runtime_minutes, genres (string array), trailer_url, trailer_provider.
Metadata fields other than identity/provider/title/genres can be null. Trailer
URL and provider are either both present or both absent. Render a trailer fallback
if unavailable. The approved development import populated 200 TMDB movies with
trailer URLs; playback availability still needs checking in the intended browser.

## Session and voting flow

1. TV restores its Auth identity and existing session before creating anything.
2. Host creates a session, displays a frontend URL such as `/join#token=...` as QR.
   Read the URL fragment on the phone and POST it in the join body. Remove it from
   browser history after joining. Never log or use an invitation token as identity.
3. Phones authenticate, join, save session_id locally, and subscribe/refetch state.
4. Host prepares queue, then starts. TV host is not a voter by default.
5. Phones heartbeat every 10 seconds and send their displayed round UUID with votes.
   Votes upsert one row per phone per round. The database advances atomically when
   every nonexcluded voter has voted; simultaneous requests cannot advance twice.
6. Host may skip with expected_round_id or end the session. Do not implement an
   additional frontend auto-advance timer or call skip when all votes appear present.

Round voters are snapshotted on opening. Late joiners wait for the next round.
After 45 seconds without a heartbeat, a phone is excluded when a vote, heartbeat,
or scheduled sweep checks the session. The sweeper runs every 10 seconds when
FastAPI is running. A returning excluded phone waits for the next round. A round
with zero votes never auto-completes; host can skip/end. An exhausted queue returns
to lobby. Sessions expire after six hours by default.

Stale vote/skip retries return the currently open round (or null) rather than
advancing twice. **200 does not guarantee that a stale vote was stored**: refetch
state and reconcile the returned round ID. A new request for a different displayed
round must be an intentional user vote; never replay an old preference automatically.
Session creation is not idempotent: after a lost creation response, recover the
host's existing sessions using its Supabase identity before creating another.

## Realtime and reconnection

Six tables are published for Supabase **Postgres Changes**. RLS, not the channel
name or client-side filter, protects data. Use `id` for group_sessions and
`session_id` for all child tables:

```js
const tables = ['group_sessions', 'session_members', 'session_movies',
  'voting_rounds', 'round_participants', 'votes'];
const channel = supabase.channel(`session:${sessionId}`);
let disposed = false;
let running = false;
let dirty = false;
async function refresh() {
  dirty = true;
  if (running) return;
  running = true;
  try {
    while (dirty && !disposed) {
      dirty = false;
      const state = await api(`/sessions/${sessionId}`);
      if (!disposed) renderState(state); // Replace with your UI state setter.
    }
  } catch (error) {
    if (!disposed) showSyncError(error); // Show retry UI; do not create a session.
  } finally {
    running = false;
  }
}
for (const table of tables) {
  channel.on('postgres_changes', {
    event: '*', schema: 'public', table,
    filter: `${table === 'group_sessions' ? 'id' : 'session_id'}=eq.${sessionId}`,
  }, refresh);
}
channel.subscribe((status) => {
  if (status === 'SUBSCRIBED') void refresh(); // Also called after rejoin.
  if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') showReconnecting();
});
// Fallback/refetch covers missed events and cross-query snapshot races.
const poll = setInterval(() => { void refresh(); }, 10000);
// On component/session cleanup:
// disposed = true; clearInterval(poll); await supabase.removeChannel(channel);
```

Subscribe first, then fetch. Coalesce events into refetches instead of patching six
arrays in arrival order. Realtime is not a durable replay log. After socket loss,
rejoin and fetch the complete current state; don't assume missed events replay.
The SDK handles token refresh; after restoring a different Auth session, update
Realtime auth/recreate subscriptions. Show reconnecting and disable stale-round
votes while state is unknown. DELETE payloads are not used for voting progression;
the service closes/updates rows instead.

Scope: the delivery/isolation test verifies INSERT/UPDATE events emitted by these
API flows. Supabase has separate DELETE-event limitations: DELETE filters and RLS
checks do not behave like INSERT/UPDATE checks, and primary-key identifiers can
be exposed by privileged deletes. There are no client DELETE grants or API delete
routes here. If private administrative deletion notifications become a requirement,
review a private Broadcast design before adding them; no schema changes for that
have been made. See [Postgres Changes limitations](https://supabase.com/docs/guides/realtime/postgres-changes).

Postgres Changes may accept an outsider's channel join; RLS must prevent **row
delivery**, and unrelated session reads return 404. This app has no private
Broadcast/Presence policies. Setting `private:true` alone does not establish
session authorization for those separate features. See [Supabase's authorization
guide](https://supabase.com/docs/guides/realtime/authorization).

### Restore the TV or a phone

Persist the session UUID separately from Supabase Auth storage. The existing
`frontend/session-client.js` helper restores the TV's identity, reads the saved
session, and verifies host_user_id. On refresh use restore() before create().
Rotate the invitation to display a new QR because raw tokens are not persisted.

Phones restore the same Auth identity and session UUID, call GET state, resume
heartbeats, subscribe, and refetch. If left_at is set, rejoin with a currently valid
invitation; a heartbeat cannot rejoin a member who deliberately left. If a lease
expired, heartbeat resumes connection but an excluded current-round slot stays
excluded. Refreshing the TV does not require phones to rejoin.

On 404, check whether the identity changed or the phone left; request a new QR when
needed. On ended/expired session show completion, not a new vote. Clearing browser
storage loses a guest identity; an invitation creates membership for the new
identity, not host ownership. No cross-device host recovery is implemented.

## Errors and retries

| Status | Actual response / action |
| --- | --- |
| 400 | `{ "detail": "Request rejected by Supabase" }`; invalid/expired invitation or database constraint; correct input/request new QR |
| 401 | Missing/malformed bearer header: `{ "detail": "Bearer token required" }`; invalid/expired Auth token: generic Supabase rejection; refresh once, otherwise restore sign-in |
| 403 | Generic Supabase rejection; not member/host/eligible, or direct writes denied; refetch and show access error |
| 404 | `{ "detail": "Session not found" }`; absent or inaccessible session, deliberately indistinguishable |
| 422 | `{ "detail": [{ "loc": [...], "msg": "...", "type": "..." }] }` for validation; skip without ID uses `{ "detail": "Skipping requires expected_round_id" }` |
| 502 | Generic Supabase rejection for otherwise unmapped upstream errors; retry with backoff, report persistent failure |
| 503 | `{ "detail": "Supabase unavailable" }` on network failures; reconnect/backoff |

Do not blindly retry create-session or rotate-invitation requests. Same-round
votes, skip with the same expected ID, queue installation, and end are idempotent
at the database boundary. POST /queue may call a provider before duplicate IDs are
ignored; provider side effects are outside that guarantee. The server logs no
upstream error bodies or credentials. Wire error responses provide deliberately
limited database detail. CORS failures are browser errors, not JSON API errors;
the backend must allow the exact frontend origin.
