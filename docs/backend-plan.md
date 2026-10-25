# Supabase backend plan

Approved scope: profiles, movie metadata and trailers, QR joins, group voting,
shown history, automatic advancement, and phone/TV realtime. Recommendation
selection belongs to the algorithm teammate. Embeddings are deferred until the
dimension and model contract are confirmed.

## Schema

| Table | Keys and constraints | Relationship / purpose |
| --- | --- | --- |
| profiles | UUID PK/FK auth.users; nonblank display_name | One identity per guest or account |
| movies | bigint identity PK; unique(provider, provider_movie_id); positive optional runtime | Metadata, genres, optional trailer_url + trailer_provider (both present or both absent) |
| group_sessions | UUID PK; host FK profiles; status lobby/active/ended; expiry after creation | Host is normally the TV; no current movie FK |
| session_members | PK(session_id,user_id); FKs session + profile; heartbeat lease, left_at, is_voter | Host display is not a voter; phones are voters |
| session_movies | PK(session_id,movie_id); FKs session + movie; unique(session_id,position); positive position | Ordered queue supplied by backend integration; shown_at NULL until displayed |
| voting_rounds | UUID PK; composite FK(session_id,movie_id) to session_movies; unique(session_id,movie_id); partial unique active session | Current round derived from the sole open round; closed reason completed/skipped/ended |
| round_participants | PK(round_id,user_id); composite FKs to round and membership | Snapshot electorate; expiry/leave marks excluded_at permanently for that round |
| votes | PK(round_id,user_id); composite FK(round_id,user_id) to electorate; value -1/+1 | A user can only vote as self through RPC |
| private.session_invites | session_id PK/FK; unique SHA-256 token hash; expiry | One rotating invitation; raw random token returned only to host |

All public tables have RLS. Authenticated users can read movie metadata, their
own profile, and rows within their joined sessions. Session members see each
other's display names and votes. Direct table mutations are denied except own
profile creation/name updates. Invoker public RPC wrappers call narrowly granted
private SECURITY DEFINER functions with fixed search_path and identity checks.
Internal advancement and expiry functions are not callable by authenticated users.

Session children cascade on session deletion. Profile deletion cascades personal
rows but is restricted while hosting a session. Referenced movie deletion is
restricted. Foreign key indexes cover reverse lookups.

## Atomic round lifecycle

Every mutation locks group_sessions first, then reads/modifies round state. The
vote carries expected round UUID. Duplicate votes upsert one row; closed-round
retries return current state without advancing again. Host skip requires the
same expected UUID. Closing a round and opening the next queued movie happen in
one transaction, protected by the lock and unique active-round index. No network
algorithm calls occur under database locks. Empty queues return to lobby rather
than invent a recommendation. A round without any votes never auto-completes.

Round voters are snapshotted from connected voting members (45-second lease).
New or returning members whose slot was excluded wait for the next round. Phones
heartbeat every 10 seconds; a FastAPI lifespan task sweeps every 10 seconds so
disconnected voters are excluded even if no further votes arrive. A heartbeat
after lease expiry does not resurrect an excluded current-round slot. If all
voters disconnect, the host may skip/end; no empty-round advancement loop occurs.

## FastAPI and recommendation boundary

Use caller JWTs and a publishable key for user RPCs, preserving auth.uid(). Never
accept a caller-supplied user_id. The sweep uses a server-only secret key; queue
preparation installs IDs through a host-checked RPC with the caller JWT.
A RecommendationProvider protocol returns an ordered list
of movie IDs from context. Mock implementation preserves supplied catalog order
and filters shown IDs; it performs no recommendation scoring or embedding work.
Queue preparation is restricted to the host and is atomic/idempotent; it does not
replace the active round. Background sweep uses service_role-only RPC.

## TV and realtime client contract

Use one Supabase browser client with persistSession:true and autoRefreshToken:true.
Restore getSession() before anonymous sign-in; do not create a user on each load.
Persist the group session UUID in localStorage, then fetch it under the restored
JWT and verify host_user_id. Never store service credentials or the QR token as
identity. Cleared storage/private browsing requires a new session (MVP limit).
Anonymous Auth must be enabled in the dashboard before guest sign-in works.

Subscribe to Postgres Changes for group_sessions, session_members, session_movies,
voting_rounds, round_participants, and votes. Use session_id filters and RLS;
subscribe then fetch a snapshot, and refetch after reconnect. Session IDs are
present on child rows for filtering and protected by composite foreign keys.
Realtime is notification, not the authority for completion or connection leases.

## Verification

Apply versioned migration to the connected project. Run rollback-only SQL checks
as authenticated users for joins, expiry, duplicate vote/skip retries, advancement,
RLS isolation, host-only operations, constraints, and publication membership. Run
a concurrent final-vote test in separate Supabase SQL transactions. Run backend unit
tests, build and lint. There are no UI files to review in this backend-only change.

Implementation: both migrations applied to tandem. Rollback SQL verification and
separate concurrent votes passed; concurrent test fixtures were removed. All eight
public application tables have RLS, six are in the realtime publication, and the
Supabase security advisor reports no findings. The TV helper is supplied for the
frontend teammate to wire into the app; rendered UI and physical phone/TV testing
remain frontend work. Live simulated Auth/API and WebSocket tests now cover a TV,
three phones, outsider authorization, reconnect recovery, and fixture-only cleanup.
The FastAPI process must run for scheduled sweeps. See frontend-integration.md,
openapi.json, and deployment-readiness.md. The approved TMDB import populated
200 movies with trailer URLs; an identical rerun inserted zero duplicates.
