-- Versioned copy lives in supabase/migrations; this file is the reviewable source.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to authenticated, service_role;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (length(btrim(display_name)) between 1 and 60),
  created_at timestamptz not null default now()
);
create table public.movies (
  id bigint generated always as identity primary key,
  provider text not null check (btrim(provider) <> ''),
  provider_movie_id text not null check (btrim(provider_movie_id) <> ''),
  title text not null check (btrim(title) <> ''),
  overview text, poster_url text, release_date date,
  runtime_minutes integer check (runtime_minutes > 0),
  genres text[] not null default '{}',
  trailer_url text check (trailer_url ~ '^https://'),
  trailer_provider text check (btrim(trailer_provider) <> ''),
  unique(provider, provider_movie_id),
  check ((trailer_url is null) = (trailer_provider is null))
);
create table public.group_sessions (
  id uuid primary key default gen_random_uuid(),
  host_user_id uuid not null references public.profiles(id),
  status text not null default 'lobby' check (status in ('lobby','active','ended')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '6 hours',
  ended_at timestamptz,
  check (expires_at > created_at),
  check ((status = 'ended') = (ended_at is not null))
);
create index group_sessions_host_idx on public.group_sessions(host_user_id);
create table public.session_members (
  session_id uuid not null references public.group_sessions(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  is_voter boolean not null default true,
  joined_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  left_at timestamptz,
  primary key(session_id,user_id),
  check (left_at is null or left_at >= joined_at)
);
create index session_members_user_idx on public.session_members(user_id,session_id);
create table public.session_movies (
  session_id uuid not null references public.group_sessions(id) on delete cascade,
  movie_id bigint not null references public.movies(id),
  position integer not null check (position > 0),
  shown_at timestamptz,
  primary key(session_id,movie_id),
  unique(session_id,position)
);
create index session_movies_movie_idx on public.session_movies(movie_id);
create table public.voting_rounds (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null,
  movie_id bigint not null,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  close_reason text check (close_reason in ('completed','skipped','ended')),
  unique(session_id,movie_id),
  unique(session_id,id),
  foreign key(session_id,movie_id) references public.session_movies(session_id,movie_id) on delete cascade,
  check ((closed_at is null) = (close_reason is null)),
  check (closed_at is null or closed_at >= opened_at)
);
create unique index one_open_round_per_session on public.voting_rounds(session_id) where closed_at is null;
create table public.round_participants (
  session_id uuid not null,
  round_id uuid not null,
  user_id uuid not null,
  excluded_at timestamptz,
  primary key(round_id,user_id),
  unique(session_id,round_id,user_id),
  foreign key(session_id,round_id) references public.voting_rounds(session_id,id) on delete cascade,
  foreign key(session_id,user_id) references public.session_members(session_id,user_id) on delete cascade
);
create index round_participants_member_idx on public.round_participants(session_id,user_id);
create table public.votes (
  session_id uuid not null,
  round_id uuid not null,
  user_id uuid not null,
  value smallint not null check (value in (-1,1)),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key(round_id,user_id),
  foreign key(session_id,round_id,user_id) references public.round_participants(session_id,round_id,user_id) on delete cascade
);
create index votes_session_idx on public.votes(session_id,round_id,user_id);
create table private.session_invites (
  session_id uuid primary key references public.group_sessions(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  check (expires_at > created_at)
);
alter table private.session_invites enable row level security;

-- Definer helpers live outside exposed schemas and never trust supplied user IDs.
create function private.is_member(p_session uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null and exists (
    select 1 from public.session_members where session_id=p_session
      and user_id=auth.uid() and left_at is null
  );
$$;
create function private.shares_session(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null and exists (
    select 1 from public.session_members a join public.session_members b using(session_id)
    where a.user_id=auth.uid() and b.user_id=p_user and a.left_at is null and b.left_at is null
  );
$$;

alter table public.profiles enable row level security;
alter table public.movies enable row level security;
alter table public.group_sessions enable row level security;
alter table public.session_members enable row level security;
alter table public.session_movies enable row level security;
alter table public.voting_rounds enable row level security;
alter table public.round_participants enable row level security;
alter table public.votes enable row level security;
revoke all on public.profiles, public.movies, public.group_sessions, public.session_members,
  public.session_movies, public.voting_rounds, public.round_participants, public.votes from anon, authenticated;
grant select on public.profiles, public.movies, public.group_sessions, public.session_members,
  public.session_movies, public.voting_rounds, public.round_participants, public.votes to authenticated;
grant insert(id,display_name), update(display_name) on public.profiles to authenticated;
grant all on public.profiles, public.movies, public.group_sessions, public.session_members,
  public.session_movies, public.voting_rounds, public.round_participants, public.votes to service_role;
grant usage, select on sequence public.movies_id_seq to service_role;
create policy profiles_read on public.profiles for select to authenticated
  using (id=(select auth.uid()) or private.shares_session(id));
create policy profiles_insert on public.profiles for insert to authenticated with check (id=(select auth.uid()));
create policy profiles_update on public.profiles for update to authenticated
  using (id=(select auth.uid())) with check (id=(select auth.uid()));
create policy movies_read on public.movies for select to authenticated using (true);
create policy sessions_read on public.group_sessions for select to authenticated using (private.is_member(id));
create policy members_read on public.session_members for select to authenticated using (private.is_member(session_id));
create policy queue_read on public.session_movies for select to authenticated using (private.is_member(session_id));
create policy rounds_read on public.voting_rounds for select to authenticated using (private.is_member(session_id));
create policy electorate_read on public.round_participants for select to authenticated using (private.is_member(session_id));
create policy votes_read on public.votes for select to authenticated using (private.is_member(session_id));

-- Internal functions are deliberately not granted to clients.
create function private.open_next(p_session uuid) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_movie bigint; v_round uuid;
begin
  select movie_id into v_movie from public.session_movies
    where session_id=p_session and shown_at is null order by position limit 1;
  if v_movie is null then
    update public.group_sessions set status='lobby' where id=p_session;
    return null;
  end if;
  insert into public.voting_rounds(session_id,movie_id) values(p_session,v_movie) returning id into v_round;
  update public.session_movies set shown_at=clock_timestamp() where session_id=p_session and movie_id=v_movie;
  insert into public.round_participants(session_id,round_id,user_id)
    select p_session,v_round,user_id from public.session_members
    where session_id=p_session and is_voter and left_at is null
      and last_seen_at > clock_timestamp()-interval '45 seconds';
  update public.group_sessions set status='active' where id=p_session;
  return v_round;
end;
$$;
create function private.check_completion(p_session uuid) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_round uuid;
begin
  -- Caller holds the session lock before reaching this function.
  if exists(select 1 from public.group_sessions where id=p_session and status<>'ended' and expires_at<=clock_timestamp()) then
    update public.voting_rounds set closed_at=clock_timestamp(),close_reason='ended' where session_id=p_session and closed_at is null;
    update public.group_sessions set status='ended',ended_at=clock_timestamp() where id=p_session;
    return null;
  end if;
  select id into v_round from public.voting_rounds where session_id=p_session and closed_at is null;
  if v_round is null then return null; end if;
  update public.round_participants p set excluded_at=clock_timestamp()
    from public.session_members m where p.round_id=v_round and p.excluded_at is null
      and m.session_id=p.session_id and m.user_id=p.user_id
      and (m.left_at is not null or m.last_seen_at<=clock_timestamp()-interval '45 seconds');
  if exists(select 1 from public.votes where round_id=v_round)
    and not exists (
      select 1 from public.round_participants p where p.round_id=v_round and p.excluded_at is null
        and not exists(select 1 from public.votes v where v.round_id=p.round_id and v.user_id=p.user_id)
    ) then
    update public.voting_rounds set closed_at=clock_timestamp(),close_reason='completed' where id=v_round;
    return private.open_next(p_session);
  end if;
  return v_round;
end;
$$;

create function private.create_session(p_name text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_id uuid; v_token text;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
  insert into public.profiles(id,display_name) values(auth.uid(),p_name)
    on conflict(id) do update set display_name=excluded.display_name;
  insert into public.group_sessions(host_user_id) values(auth.uid()) returning id into v_id;
  insert into public.session_members(session_id,user_id,is_voter) values(v_id,auth.uid(),false);
  v_token := replace(gen_random_uuid()::text,'-','') || replace(gen_random_uuid()::text,'-','');
  insert into private.session_invites(session_id,token_hash,expires_at)
    values(v_id,encode(sha256(convert_to(v_token,'UTF8')),'hex'),clock_timestamp()+interval '6 hours');
  return jsonb_build_object('session_id',v_id,'invite_token',v_token);
end;
$$;
create function private.join_session(p_token text,p_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_id uuid;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
  if p_token is null or length(p_token)<>64 then raise exception 'Invalid invitation' using errcode='22023'; end if;
  select session_id into v_id from private.session_invites
    where token_hash=encode(sha256(convert_to(p_token,'UTF8')),'hex') and expires_at>clock_timestamp();
  perform 1 from public.group_sessions where id=v_id and status<>'ended' and expires_at>clock_timestamp() for update;
  if not found then raise exception 'Invalid or expired invitation' using errcode='22023'; end if;
  insert into public.profiles(id,display_name) values(auth.uid(),p_name)
    on conflict(id) do update set display_name=excluded.display_name;
  -- Check expiry before reconnecting; an expired electorate slot stays excluded.
  perform private.check_completion(v_id);
  insert into public.session_members(session_id,user_id) values(v_id,auth.uid())
    on conflict(session_id,user_id) do update set left_at=null,last_seen_at=clock_timestamp();
  return v_id;
end;
$$;
create function private.rotate_invite(p_session uuid) returns text
language plpgsql security definer set search_path = '' as $$
declare v_token text; v_expiry timestamptz;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
  select expires_at into v_expiry from public.group_sessions where id=p_session
    and host_user_id=auth.uid() and status<>'ended' and expires_at>clock_timestamp() for update;
  if not found then raise exception 'Host required' using errcode='42501'; end if;
  v_token := replace(gen_random_uuid()::text,'-','') || replace(gen_random_uuid()::text,'-','');
  update private.session_invites set token_hash=encode(sha256(convert_to(v_token,'UTF8')),'hex'),
    created_at=clock_timestamp(),expires_at=v_expiry where session_id=p_session;
  return v_token;
end;
$$;
create function private.heartbeat(p_session uuid,p_leave boolean) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_round uuid;
begin
  if not private.is_member(p_session) then raise exception 'Membership required' using errcode='42501'; end if;
  perform 1 from public.group_sessions where id=p_session for update;
  v_round := private.check_completion(p_session);
  update public.session_members set last_seen_at=clock_timestamp(),
    left_at=case when p_leave then clock_timestamp() else null end
    where session_id=p_session and user_id=auth.uid();
  if p_leave then v_round := private.check_completion(p_session); end if;
  return v_round;
end;
$$;
create function private.cast_vote(p_session uuid,p_round uuid,p_value smallint) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_current uuid;
begin
  if not private.is_member(p_session) then raise exception 'Membership required' using errcode='42501'; end if;
  if p_value is null or p_value not in (-1,1) then raise exception 'Vote must be -1 or 1' using errcode='22023'; end if;
  perform 1 from public.group_sessions where id=p_session for update;
  v_current := private.check_completion(p_session);
  if p_round is distinct from v_current then return v_current; end if;
  if not exists(select 1 from public.round_participants where round_id=p_round and user_id=auth.uid() and excluded_at is null) then
    raise exception 'Not eligible for this round' using errcode='42501';
  end if;
  update public.session_members set last_seen_at=clock_timestamp() where session_id=p_session and user_id=auth.uid();
  insert into public.votes(session_id,round_id,user_id,value) values(p_session,p_round,auth.uid(),p_value)
    on conflict(round_id,user_id) do update set value=excluded.value,updated_at=clock_timestamp();
  return private.check_completion(p_session);
end;
$$;
create function private.control_session(p_session uuid,p_expected_round uuid,p_action text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_current uuid; v_status text;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
  select status into v_status from public.group_sessions where id=p_session and host_user_id=auth.uid() for update;
  if not found then raise exception 'Host required' using errcode='42501'; end if;
  if p_action is null or p_action not in ('start','skip','end') then raise exception 'Invalid action' using errcode='22023'; end if;
  if v_status='ended' then return null; end if;
  select id into v_current from public.voting_rounds where session_id=p_session and closed_at is null;
  if p_action='end' then
    update public.voting_rounds set closed_at=clock_timestamp(),close_reason='ended' where id=v_current;
    update public.group_sessions set status='ended',ended_at=clock_timestamp() where id=p_session;
    return null;
  end if;
  if exists(select 1 from public.group_sessions where id=p_session and expires_at<=clock_timestamp()) then
    return private.check_completion(p_session);
  end if;
  if p_action='start' then
    if v_current is not null then return v_current; end if;
    return private.open_next(p_session);
  end if;
  if v_current is null or p_expected_round is distinct from v_current then return v_current; end if;
  update public.voting_rounds set closed_at=clock_timestamp(),close_reason='skipped' where id=v_current;
  return private.open_next(p_session);
end;
$$;

-- Queue is prepared outside the transaction by the recommendation integration.
-- Caller JWT remains attached so only the host can install the resulting queue.
create function private.enqueue_movies(p_session uuid,p_movies bigint[]) returns integer
language plpgsql security definer set search_path = '' as $$
declare v_position integer; v_movie bigint; v_count integer := 0;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
  perform 1 from public.group_sessions where id=p_session and host_user_id=auth.uid()
    and status<>'ended' and expires_at>clock_timestamp() for update;
  if not found then raise exception 'Active session host required' using errcode='42501'; end if;
  if p_movies is null or cardinality(p_movies)>100 then raise exception 'Queue limit is 100 per request' using errcode='22023'; end if;
  select coalesce(max(position),0) into v_position from public.session_movies where session_id=p_session;
  foreach v_movie in array p_movies loop
    if not exists(select 1 from public.session_movies where session_id=p_session and movie_id=v_movie) then
      v_position:=v_position+1;
      insert into public.session_movies(session_id,movie_id,position) values(p_session,v_movie,v_position);
      v_count:=v_count+1;
    end if;
  end loop;
  return v_count;
end;
$$;
create function private.sweep_sessions() returns integer
language plpgsql security definer set search_path = '' as $$
declare v_id uuid; v_count integer := 0;
begin
  -- No user-supplied identity is accepted by this service-role-only worker.
  for v_id in select id from public.group_sessions where status<>'ended' order by id for update skip locked loop
    perform private.check_completion(v_id);
    v_count:=v_count+1;
  end loop;
  return v_count;
end;
$$;

create function public.create_session(p_name text) returns jsonb language sql security invoker set search_path='' as $$ select private.create_session(p_name); $$;
create function public.join_session(p_token text,p_name text) returns uuid language sql security invoker set search_path='' as $$ select private.join_session(p_token,p_name); $$;
create function public.rotate_invite(p_session uuid) returns text language sql security invoker set search_path='' as $$ select private.rotate_invite(p_session); $$;
create function public.heartbeat(p_session uuid,p_leave boolean default false) returns uuid language sql security invoker set search_path='' as $$ select private.heartbeat(p_session,p_leave); $$;
create function public.cast_vote(p_session uuid,p_round uuid,p_value smallint) returns uuid language sql security invoker set search_path='' as $$ select private.cast_vote(p_session,p_round,p_value); $$;
create function public.control_session(p_session uuid,p_expected_round uuid,p_action text) returns uuid language sql security invoker set search_path='' as $$ select private.control_session(p_session,p_expected_round,p_action); $$;
create function public.enqueue_movies(p_session uuid,p_movies bigint[]) returns integer language sql security invoker set search_path='' as $$ select private.enqueue_movies(p_session,p_movies); $$;
create function public.sweep_sessions() returns integer language sql security invoker set search_path='' as $$ select private.sweep_sessions(); $$;

revoke all on function private.is_member(uuid), private.shares_session(uuid),
  private.open_next(uuid), private.check_completion(uuid), private.create_session(text),
  private.join_session(text,text), private.rotate_invite(uuid), private.heartbeat(uuid,boolean),
  private.cast_vote(uuid,uuid,smallint), private.control_session(uuid,uuid,text),
  private.enqueue_movies(uuid,bigint[]), private.sweep_sessions() from public, anon, authenticated;
revoke all on function public.create_session(text), public.join_session(text,text),
  public.rotate_invite(uuid), public.heartbeat(uuid,boolean), public.cast_vote(uuid,uuid,smallint),
  public.control_session(uuid,uuid,text), public.enqueue_movies(uuid,bigint[]), public.sweep_sessions() from public, anon, authenticated;
grant execute on function private.is_member(uuid), private.shares_session(uuid),
  private.create_session(text), private.join_session(text,text), private.rotate_invite(uuid),
  private.heartbeat(uuid,boolean), private.cast_vote(uuid,uuid,smallint),
  private.control_session(uuid,uuid,text), private.enqueue_movies(uuid,bigint[]) to authenticated;
grant execute on function public.create_session(text), public.join_session(text,text),
  public.rotate_invite(uuid), public.heartbeat(uuid,boolean), public.cast_vote(uuid,uuid,smallint),
  public.control_session(uuid,uuid,text), public.enqueue_movies(uuid,bigint[]) to authenticated;
grant execute on function private.sweep_sessions(), public.sweep_sessions() to service_role;

alter publication supabase_realtime add table public.group_sessions, public.session_members,
  public.session_movies, public.voting_rounds, public.round_participants, public.votes;
