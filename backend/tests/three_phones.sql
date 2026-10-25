-- Rollback-only TV + three-phone database integration. No existing rows are changed.
begin;
create temporary table actors(role text primary key, id uuid default gen_random_uuid());
insert into actors(role) values('tv'),('alice'),('bob'),('carol'),('outsider');
insert into auth.users(id) select id from actors;
create temporary table ctx(k text primary key,v text);
grant select on actors to authenticated;
grant all on ctx to authenticated;
create function pg_temp.check_ok(ok boolean,label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'FAIL: %',label; end if; end $$;
with inserted as (
  insert into public.movies(provider,provider_movie_id,title)
  select 'rollback_test',gen_random_uuid()::text,'Fixture '||n from generate_series(1,5) n
  returning id
) insert into ctx select 'movies',string_agg(id::text,',' order by id) from inserted;
set local role authenticated;
select set_config('request.jwt.claim.sub',(select id::text from actors where role='tv'),true);
with created as(select public.create_session('TV') data)
insert into ctx select 'session',data->>'session_id' from created
union all select 'token',data->>'invite_token' from created;
do $$ declare person text; begin
  foreach person in array array['alice','bob','carol'] loop
    perform set_config('request.jwt.claim.sub',(select id::text from actors where role=person),true);
    perform public.join_session((select v from ctx where k='token'),person);
  end loop;
end $$;
select pg_temp.check_ok((select count(*)=4 from public.session_members
  where session_id=(select v::uuid from ctx where k='session')),'TV and three phones joined');
select set_config('request.jwt.claim.sub',(select id::text from actors where role='tv'),true);
select public.enqueue_movies((select v::uuid from ctx where k='session'),
  string_to_array((select v from ctx where k='movies'),',')::bigint[]);
insert into ctx values('first',public.control_session((select v::uuid from ctx where k='session'),null,'start')::text);
do $$ declare person text; begin
  foreach person in array array['alice','bob'] loop
    perform set_config('request.jwt.claim.sub',(select id::text from actors where role=person),true);
    perform public.cast_vote((select v::uuid from ctx where k='session'),(select v::uuid from ctx where k='first'),1::smallint);
  end loop;
end $$;
select pg_temp.check_ok((select count(*)=1 from public.voting_rounds
  where session_id=(select v::uuid from ctx where k='session')),'waits for third phone');
select set_config('request.jwt.claim.sub',(select id::text from actors where role='carol'),true);
select public.cast_vote((select v::uuid from ctx where k='session'),(select v::uuid from ctx where k='first'),(-1)::smallint);
select pg_temp.check_ok((select count(*)=2 from public.voting_rounds
  where session_id=(select v::uuid from ctx where k='session')),'third vote advances');
insert into ctx select 'second',id::text from public.voting_rounds
  where session_id=(select v::uuid from ctx where k='session') and closed_at is null;
do $$ declare person text; begin
  foreach person in array array['alice','bob'] loop
    perform set_config('request.jwt.claim.sub',(select id::text from actors where role=person),true);
    perform public.cast_vote((select v::uuid from ctx where k='session'),(select v::uuid from ctx where k='second'),1::smallint);
  end loop;
end $$;
reset role;
-- Scoped expiry simulation only affects this run's Carol row.
update public.session_members set last_seen_at=clock_timestamp()-interval '60 seconds'
  where session_id=(select v::uuid from ctx where k='session')
    and user_id=(select id from actors where role='carol');
select 1 from public.group_sessions where id=(select v::uuid from ctx where k='session') for update;
select private.check_completion((select v::uuid from ctx where k='session'));
set local role authenticated;
select set_config('request.jwt.claim.sub',(select id::text from actors where role='tv'),true);
select pg_temp.check_ok((select count(*)=3 from public.voting_rounds
  where session_id=(select v::uuid from ctx where k='session')),'expired Carol cannot block round');
insert into ctx select 'third',id::text from public.voting_rounds
  where session_id=(select v::uuid from ctx where k='session') and closed_at is null;
select set_config('request.jwt.claim.sub',(select id::text from actors where role='outsider'),true);
select pg_temp.check_ok((select count(*)=0 from public.group_sessions
  where id=(select v::uuid from ctx where k='session')),'outsider cannot read session');
do $$ begin
  begin
    perform public.control_session((select v::uuid from ctx where k='session'),(select v::uuid from ctx where k='third'),'skip');
    raise exception 'FAIL: outsider skip accepted';
  exception when insufficient_privilege then null; end;
  begin
    perform public.cast_vote((select v::uuid from ctx where k='session'),(select v::uuid from ctx where k='third'),1::smallint);
    raise exception 'FAIL: outsider vote accepted';
  exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub',(select id::text from actors where role='alice'),true);
do $$ begin
  begin
    update public.votes set value=-1 where session_id=(select v::uuid from ctx where k='session')
      and user_id=(select id from actors where role='bob');
    raise exception 'FAIL: other user vote update accepted';
  exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub',(select id::text from actors where role='tv'),true);
select public.control_session((select v::uuid from ctx where k='session'),(select v::uuid from ctx where k='third'),'skip');
select public.control_session((select v::uuid from ctx where k='session'),(select v::uuid from ctx where k='third'),'skip');
select pg_temp.check_ok((select count(*)=4 from public.voting_rounds
  where session_id=(select v::uuid from ctx where k='session')),'host skip retry advances once');
select public.control_session((select v::uuid from ctx where k='session'),null,'end');
select pg_temp.check_ok((select status='ended' from public.group_sessions
  where id=(select v::uuid from ctx where k='session')),'host terminates session');
select pg_temp.check_ok((select count(*)=0 from public.voting_rounds
  where session_id=(select v::uuid from ctx where k='session') and closed_at is null),'no open round after end');
reset role;
set local role anon;
do $$ begin
  begin
    perform public.create_session('Unauthenticated');
    raise exception 'FAIL: unauthenticated create accepted';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
rollback;
select 'PASS: TV + three phones, voting, advancement, expiry, host skip/end, RLS; fixtures rolled back' as result;
