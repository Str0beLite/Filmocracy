-- Run as postgres via Supabase execute_sql or psql. All fixtures roll back.
begin;
create temporary table test_context(k text primary key,v text);
grant select,insert,update on test_context to authenticated;
create function pg_temp.check_ok(ok boolean,label text) returns void language plpgsql as $$
begin
  if ok is distinct from true then raise exception 'FAILED: %',label; end if;
end;
$$;
insert into test_context values ('host',gen_random_uuid()::text),('alice',gen_random_uuid()::text),
  ('bob',gen_random_uuid()::text),('outsider',gen_random_uuid()::text);
insert into auth.users(id) select v::uuid from test_context;
with inserted as (
  insert into public.movies(provider,provider_movie_id,title,trailer_url,trailer_provider)
    select 'verification',gen_random_uuid()::text,'Verification '||n,
      'https://www.youtube.com/watch?v=mock','youtube' from generate_series(1,5) n
    returning id
) insert into test_context select 'movies',string_agg(id::text,',' order by id) from inserted;

set local role authenticated;
select set_config('request.jwt.claim.sub',(select v from test_context where k='host'),true);
with created as (select public.create_session('TV') data)
insert into test_context select 'session',data->>'session_id' from created
union all select 'token',data->>'invite_token' from created;
select pg_temp.check_ok((select count(*)=1 from public.group_sessions),'host can read own session');
select pg_temp.check_ok(not has_table_privilege('authenticated','private.session_invites','SELECT'),'no invitation read grant');
select public.enqueue_movies((select v::uuid from test_context where k='session'),
  string_to_array((select v from test_context where k='movies'),',')::bigint[]);
select pg_temp.check_ok(public.enqueue_movies((select v::uuid from test_context where k='session'),
  string_to_array((select v from test_context where k='movies'),',')::bigint[])=0,'queue is idempotent');

select set_config('request.jwt.claim.sub',(select v from test_context where k='alice'),true);
select public.join_session((select v from test_context where k='token'),'Alice');
select set_config('request.jwt.claim.sub',(select v from test_context where k='bob'),true);
select public.join_session((select v from test_context where k='token'),'Bob');
select pg_temp.check_ok((select count(*)=3 from public.session_members),'QR joined host and two voters');
do $$ begin
  begin
    perform public.control_session((select v::uuid from test_context where k='session'),null,'start');
    raise exception 'FAILED: participant start accepted';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sweep_sessions();
    raise exception 'FAILED: participant sweep accepted';
  exception when insufficient_privilege then null; end;
  begin
    perform public.join_session(repeat('0',64),'Invalid');
    raise exception 'FAILED: bad invitation accepted';
  exception when invalid_parameter_value then null; end;
end $$;

select set_config('request.jwt.claim.sub',(select v from test_context where k='host'),true);
insert into test_context values('round1',public.control_session((select v::uuid from test_context where k='session'),null,'start')::text);
select pg_temp.check_ok((select count(*)=2 from public.round_participants),'TV excluded from electorate');
select pg_temp.check_ok((select count(*)=1 from public.session_movies where shown_at is not null),'only presented movie marked shown');
select set_config('request.jwt.claim.sub',(select v from test_context where k='alice'),true);
select public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round1'),1::smallint);
select public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round1'),(-1)::smallint);
select pg_temp.check_ok((select count(*)=1 from public.votes),'duplicate vote upserts');
select pg_temp.check_ok((select count(*)=1 from public.voting_rounds),'waits for remaining voter');
do $$ begin
  begin
    update public.votes set user_id=(select v::uuid from test_context where k='bob');
    raise exception 'FAILED: direct vote mutation accepted';
  exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub',(select v from test_context where k='bob'),true);
select public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round1'),1::smallint);
select pg_temp.check_ok((select count(*)=2 from public.voting_rounds),'final vote automatically advances');
select pg_temp.check_ok((select count(*)=1 from public.voting_rounds where closed_at is null),'exactly one open round');
select public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round1'),1::smallint);
select pg_temp.check_ok((select count(*)=2 from public.voting_rounds),'stale vote cannot advance twice');
insert into test_context select 'round2',id::text from public.voting_rounds where closed_at is null;

select set_config('request.jwt.claim.sub',(select v from test_context where k='outsider'),true);
select pg_temp.check_ok((select count(*)=0 from public.group_sessions),'outsider cannot read sessions');
select pg_temp.check_ok((select count(*)=0 from public.session_members),'outsider cannot read members');
select pg_temp.check_ok((select count(*)=0 from public.session_movies),'outsider cannot read history');
select pg_temp.check_ok((select count(*)=0 from public.voting_rounds),'outsider cannot read rounds');
select pg_temp.check_ok((select count(*)=0 from public.round_participants),'outsider cannot read electorate');
select pg_temp.check_ok((select count(*)=0 from public.votes),'outsider cannot read votes');
select pg_temp.check_ok((select count(*)=0 from public.profiles),'outsider cannot read profiles');
do $$ begin
  begin
    perform public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round2'),1::smallint);
    raise exception 'FAILED: outsider vote accepted';
  exception when insufficient_privilege then null; end;
end $$;

-- Simulate a participant lost for >45 seconds. Sweep must advance without them.
reset role;
update public.session_members set last_seen_at=clock_timestamp()-interval '60 seconds'
  where user_id=(select v::uuid from test_context where k='bob');
set local role authenticated;
select set_config('request.jwt.claim.sub',(select v from test_context where k='alice'),true);
select public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round2'),1::smallint);
select pg_temp.check_ok((select count(*)=3 from public.voting_rounds),'disconnected voter does not block');
select pg_temp.check_ok((select excluded_at is not null from public.round_participants
  where round_id=(select v::uuid from test_context where k='round2') and user_id=(select v::uuid from test_context where k='bob')),'expired slot excluded');
insert into test_context select 'round3',id::text from public.voting_rounds where closed_at is null;
select set_config('request.jwt.claim.sub',(select v from test_context where k='bob'),true);
select public.heartbeat((select v::uuid from test_context where k='session'));
do $$ begin
  begin
    perform public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round3'),1::smallint);
    raise exception 'FAILED: returning voter added mid-round';
  exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub',(select v from test_context where k='host'),true);
select public.control_session((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round3'),'skip');
select public.control_session((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round3'),'skip');
select pg_temp.check_ok((select count(*)=4 from public.voting_rounds),'duplicate skip cannot advance twice');
insert into test_context select 'round4',id::text from public.voting_rounds where closed_at is null;
select pg_temp.check_ok((select count(*)=2 from public.round_participants where round_id=(select v::uuid from test_context where k='round4')),'returning voter included next round');

-- Alice votes, then Bob disconnects; only the scheduled sweep can finish it.
select set_config('request.jwt.claim.sub',(select v from test_context where k='alice'),true);
select public.cast_vote((select v::uuid from test_context where k='session'),(select v::uuid from test_context where k='round4'),1::smallint);
reset role;
update public.session_members set last_seen_at=clock_timestamp()-interval '60 seconds'
  where user_id=(select v::uuid from test_context where k='bob');
set local role service_role;
select public.sweep_sessions();
reset role;
select pg_temp.check_ok((select count(*)=5 from public.voting_rounds),'sweep completes stalled round');

set local role authenticated;
select set_config('request.jwt.claim.sub',(select v from test_context where k='host'),true);
insert into test_context values('new_token',public.rotate_invite((select v::uuid from test_context where k='session')));
select set_config('request.jwt.claim.sub',(select v from test_context where k='outsider'),true);
do $$ begin
  begin
    perform public.join_session((select v from test_context where k='token'),'Outsider');
    raise exception 'FAILED: revoked invitation accepted';
  exception when invalid_parameter_value then null; end;
end $$;
select set_config('request.jwt.claim.sub',(select v from test_context where k='host'),true);
select public.control_session((select v::uuid from test_context where k='session'),null,'end');
select pg_temp.check_ok((select status='ended' from public.group_sessions),'host ends session');
select pg_temp.check_ok((select count(*)=0 from public.voting_rounds where closed_at is null),'end closes round');
select set_config('request.jwt.claim.sub',(select v from test_context where k='outsider'),true);
do $$ begin
  begin
    perform public.join_session((select v from test_context where k='new_token'),'Outsider');
    raise exception 'FAILED: ended session allowed join';
  exception when invalid_parameter_value then null; end;
end $$;
select set_config('request.jwt.claim.sub',(select v from test_context where k='host'),true);
with created as(select public.create_session('Expiry TV') data)
insert into test_context select 'expiry_session',data->>'session_id' from created
union all select 'expiry_token',data->>'invite_token' from created;
select public.enqueue_movies((select v::uuid from test_context where k='expiry_session'),
  string_to_array((select v from test_context where k='movies'),',')::bigint[]);
select public.control_session((select v::uuid from test_context where k='expiry_session'),null,'start');
reset role;
update private.session_invites set created_at=clock_timestamp()-interval '2 minutes',
  expires_at=clock_timestamp()-interval '1 minute'
  where session_id=(select v::uuid from test_context where k='expiry_session');
set local role authenticated;
select set_config('request.jwt.claim.sub',(select v from test_context where k='outsider'),true);
do $$ begin
  begin
    perform public.join_session((select v from test_context where k='expiry_token'),'Outsider');
    raise exception 'FAILED: expired invitation allowed join';
  exception when invalid_parameter_value then null; end;
end $$;
reset role;
set local role service_role;
select public.sweep_sessions();
reset role;
select pg_temp.check_ok((select count(*)=1 from public.voting_rounds
  where session_id=(select v::uuid from test_context where k='expiry_session')),'zero voters cannot cause advancement loop');
update public.group_sessions set created_at=clock_timestamp()-interval '2 hours',
  expires_at=clock_timestamp()-interval '1 hour'
  where id=(select v::uuid from test_context where k='expiry_session');
set local role service_role;
select public.sweep_sessions();
reset role;
select pg_temp.check_ok((select status='ended' from public.group_sessions
  where id=(select v::uuid from test_context where k='expiry_session')),'sweep ends expired sessions');

-- Database constraints and deployment configuration.
do $$ begin
  begin
    insert into public.movies(provider,provider_movie_id,title,trailer_url) values('test',gen_random_uuid()::text,'Bad','https://example.com');
    raise exception 'FAILED: unpaired trailer accepted';
  exception when check_violation then null; end;
  begin
    insert into public.votes(session_id,round_id,user_id,value)
      values((select v::uuid from test_context where k='session'),gen_random_uuid(),(select v::uuid from test_context where k='alice'),1);
    raise exception 'FAILED: orphan vote accepted';
  exception when foreign_key_violation then null; end;
end $$;
select pg_temp.check_ok((select count(*)=8 and bool_and(relrowsecurity) from pg_class
  where relnamespace='public'::regnamespace and relkind='r' and relname in
  ('profiles','movies','group_sessions','session_members','session_movies','voting_rounds','round_participants','votes')),'all application tables enforce RLS');
select pg_temp.check_ok((select count(*)=6 from pg_publication_tables where pubname='supabase_realtime'
  and schemaname='public' and tablename in ('group_sessions','session_members','session_movies','voting_rounds','round_participants','votes')),'six realtime tables published');
select pg_temp.check_ok(to_regclass('public.user_preference_embeddings') is null,'embeddings deferred');
rollback;
select 'PASS: database authorization, constraints, lifecycle, disconnect sweep, retries, realtime' as result;
