// Demo engine: a scripted movie night with three fake friends.
// Loaded first. The .jsx files run as classic scripts, so the hooks pulled out
// here (and every top-level function) are shared across files.
const { useState, useEffect, useReducer, useMemo } = React;
const D = window.TANDEM;

const TRAILER_MS = 12000;
const MISS_PAUSE_MS = 4500;
const ANALYZE_MS = 3900;
const FRIENDS = D.people.filter((p) => p.id !== 'you');

const pick = (list) => list[Math.floor(Math.random() * list.length)];

let reactionSeq = 0;
function makeReaction(who, emoji) {
  return { id: ++reactionSeq, who, emoji, dx: `${(Math.random() * 6 - 3).toFixed(1)}cqw` };
}

function initialState() {
  return {
    run: Date.now(), // changes on restart so the lobby timers run again
    phase: 'lobby', // lobby → trailer → voting → reveal → result (→ showing)
    phoneStep: 'scan', // scan → connect → analyzing → vibe → seated
    youName: '',
    seated: [],
    movieIdx: 0,
    trailerEndsAt: 0,
    votes: {},
    revealed: 0,
    reactions: [],
  };
}

function reducer(s, a) {
  switch (a.type) {
    case 'restart':
      return initialState();
    case 'scan':
      return s.phoneStep === 'scan' ? { ...s, phoneStep: 'connect' } : s;
    case 'phoneStep':
      return { ...s, phoneStep: a.step };
    case 'setName':
      return { ...s, youName: a.name };
    case 'seat':
      return s.seated.includes(a.id) ? s : { ...s, seated: [...s.seated, a.id] };
    case 'playTrailer':
      return {
        ...s,
        phase: 'trailer',
        movieIdx: a.movieIdx,
        trailerEndsAt: a.now + TRAILER_MS,
        votes: {},
        revealed: 0,
        reactions: [],
      };
    case 'endTrailer':
      return s.phase === 'trailer' ? { ...s, phase: 'voting' } : s;
    case 'vote':
      return s.phase === 'voting' && !s.votes[a.id] ? { ...s, votes: { ...s.votes, [a.id]: a.vote } } : s;
    case 'reveal':
      return { ...s, phase: 'reveal', revealed: 0 };
    case 'revealNext':
      return { ...s, revealed: s.revealed + 1 };
    case 'result':
      return { ...s, phase: 'result' };
    case 'showMovie':
      return { ...s, phase: 'showing' };
    case 'react':
      return s.phase === 'trailer' ? { ...s, reactions: [...s.reactions.slice(-23), a.reaction] } : s;
    default:
      return s;
  }
}

function useMovieNight() {
  const [s, dispatch] = useReducer(reducer, undefined, initialState);
  const movie = D.movies[s.movieIdx];
  const everyone = D.people.length;
  const voteCount = Object.keys(s.votes).length;
  const yesCount = Object.values(s.votes).filter((v) => v === 'yes').length;
  const unanimous = voteCount === everyone && yesCount === everyone;
  const nextIdx = (s.movieIdx + 1) % D.movies.length;

  // Reveal the yeses first, so a lone "no" lands last.
  const revealOrder = useMemo(
    () => [...D.people].sort((a, b) => (s.votes[a.id] === 'no') - (s.votes[b.id] === 'no')).map((p) => p.id),
    [s.votes],
  );

  // Friends trickle into the lobby.
  useEffect(() => {
    const timers = FRIENDS.map((f) => setTimeout(() => dispatch({ type: 'seat', id: f.id }), f.joinAt));
    return () => timers.forEach(clearTimeout);
  }, [s.run]);

  // The phone "reads" Instagram for a few seconds.
  useEffect(() => {
    if (s.phoneStep !== 'analyzing') return;
    const t = setTimeout(() => dispatch({ type: 'phoneStep', step: 'vibe' }), ANALYZE_MS);
    return () => clearTimeout(t);
  }, [s.phoneStep]);

  // Trailer runs out on its own; friends react while it plays.
  useEffect(() => {
    if (s.phase !== 'trailer') return;
    const end = setTimeout(() => dispatch({ type: 'endTrailer' }), s.trailerEndsAt - Date.now());
    let t;
    const tick = () => {
      dispatch({ type: 'react', reaction: makeReaction(pick(FRIENDS).id, pick(movie.vibes)) });
      t = setTimeout(tick, 600 + Math.random() * 900);
    };
    t = setTimeout(tick, 1200);
    return () => {
      clearTimeout(end);
      clearTimeout(t);
    };
  }, [s.phase, s.trailerEndsAt]);

  // Friends vote a beat after the trailer ends.
  useEffect(() => {
    if (s.phase !== 'voting') return;
    const timers = FRIENDS.map((f, i) =>
      setTimeout(() => dispatch({ type: 'vote', id: f.id, vote: movie.votes[f.id] }), 700 + i * 600 + Math.random() * 400),
    );
    return () => timers.forEach(clearTimeout);
  }, [s.phase, s.movieIdx]);

  useEffect(() => {
    if (s.phase !== 'voting' || voteCount < everyone) return;
    const t = setTimeout(() => dispatch({ type: 'reveal' }), 700);
    return () => clearTimeout(t);
  }, [s.phase, voteCount]);

  // Flip seats one at a time, then land on the result.
  useEffect(() => {
    if (s.phase !== 'reveal') return;
    const done = s.revealed >= everyone;
    const t = setTimeout(
      () => dispatch({ type: done ? 'result' : 'revealNext' }),
      done ? 800 : s.revealed === 0 ? 450 : 550,
    );
    return () => clearTimeout(t);
  }, [s.phase, s.revealed]);

  // No golden buzzer: roll on to the next trailer.
  useEffect(() => {
    if (s.phase !== 'result' || unanimous) return;
    const t = setTimeout(() => dispatch({ type: 'playTrailer', movieIdx: nextIdx, now: Date.now() }), MISS_PAUSE_MS);
    return () => clearTimeout(t);
  }, [s.phase, unanimous, nextIdx]);

  return {
    s,
    dispatch,
    movie,
    unanimous,
    voteCount,
    yesCount,
    revealOrder,
    everyoneSeated: D.people.every((p) => s.seated.includes(p.id)),
    start: () => dispatch({ type: 'playTrailer', movieIdx: s.movieIdx, now: Date.now() }),
    nextTrailer: () => dispatch({ type: 'playTrailer', movieIdx: nextIdx, now: Date.now() }),
    react: (who, emoji) => dispatch({ type: 'react', reaction: makeReaction(who, emoji) }),
    vote: (vote) => dispatch({ type: 'vote', id: 'you', vote }),
  };
}
