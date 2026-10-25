// Demo engine: a scripted movie night with three fake friends.
// Loaded first. The .jsx files run as classic scripts, so the hooks pulled out
// here (and every top-level function) are shared across files.
const { useState, useEffect, useReducer, useMemo } = React;
const D = window.TANDEM;

const TRAILER_MS = 12000;
const REVEAL_MS = 1800;
const MISS_PAUSE_MS = 4500;
const ANALYZE_MS = 3600;
const FRIENDS = D.people.filter((p) => p.id !== 'you');

const pick = (list) => list[Math.floor(Math.random() * list.length)];

let reactionSeq = 0;
function makeReaction(who, emoji) {
  return { id: ++reactionSeq, who, emoji, dx: `${(Math.random() * 6 - 3).toFixed(1)}cqw` };
}

// A loading bar for "how close are we to tonight's movie", not a real model
// score. Seating everyone fills the first 30%, each vote round eases closer,
// votes coming in nudge it along, and it only hits 100% once there's a pick.
function completionStatus(s) {
  if (s.phase === 'picks' || s.phase === 'showing' || s.history.some((r) => r.unanimous)) return 100;
  const setup = 30 * (s.seated.length / D.people.length);
  const after = (rounds) => setup + (100 - setup) * (1 - Math.pow(0.6, rounds)) * 0.92;
  let c = after(s.history.length);
  if (s.phase === 'voting' || s.phase === 'reveal') {
    c += (after(s.history.length + 1) - c) * 0.5 * (Object.keys(s.votes).length / D.people.length);
  }
  return Math.round(c);
}

// Trailers the group voted on rank by votes (golden buzzers first); ones not
// shown yet rank by the model's prediction, discounted for being unseen.
// Only the order is shown, never the votes behind it.
function rankPicks(history) {
  const latest = Object.fromEntries(history.map((h) => [h.movieIdx, h]));
  return D.movies
    .map((movie, i) => {
      const round = latest[i];
      if (!round) return { movie, round: null, score: (movie.match / 100) * 0.8 };
      return { movie, round, score: round.yes / round.total + (round.unanimous ? 1 : 0) };
    })
    .sort((a, b) => b.score - a.score);
}

function initialState() {
  return {
    run: Date.now(), // changes on restart so the lobby timers run again
    phase: 'lobby', // lobby → trailer → voting → reveal → result → picks → showing
    phoneStep: 'scan', // scan → mood → connect → analyzing → seated
    youName: '',
    youMood: null,
    seated: [],
    movieIdx: 0,
    trailerEndsAt: 0,
    votes: {},
    reactions: [],
    history: [], // one entry per finished vote round
    nowShowing: null,
  };
}

function reducer(s, a) {
  switch (a.type) {
    case 'restart':
      return initialState();
    case 'scan':
      return s.phoneStep === 'scan' ? { ...s, phoneStep: 'mood' } : s;
    case 'phoneStep':
      return { ...s, phoneStep: a.step };
    case 'setName':
      return { ...s, youName: a.name };
    case 'setMood':
      return { ...s, youMood: a.mood };
    case 'seat':
      return s.seated.includes(a.id) ? s : { ...s, seated: [...s.seated, a.id] };
    case 'youSeated':
      return { ...s, phoneStep: 'seated', seated: s.seated.includes('you') ? s.seated : [...s.seated, 'you'] };
    case 'playTrailer':
      return { ...s, phase: 'trailer', movieIdx: a.movieIdx, trailerEndsAt: a.now + TRAILER_MS, votes: {}, reactions: [] };
    case 'endTrailer':
      return s.phase === 'trailer' ? { ...s, phase: 'voting' } : s;
    case 'vote':
      return s.phase === 'voting' && !s.votes[a.id] ? { ...s, votes: { ...s.votes, [a.id]: a.vote } } : s;
    case 'reveal':
      return { ...s, phase: 'reveal' };
    case 'result': {
      const total = D.people.length;
      const yes = Object.values(s.votes).filter((v) => v === 'yes').length;
      const round = { movieIdx: s.movieIdx, yes, total, unanimous: yes === total };
      return { ...s, phase: 'result', history: [...s.history, round] };
    }
    case 'showPicks':
      return { ...s, phase: 'picks' };
    case 'showMovie':
      return { ...s, phase: 'showing', nowShowing: a.movie };
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
  const unanimous = voteCount === everyone && Object.values(s.votes).every((v) => v === 'yes');
  const hasNext = s.movieIdx < D.movies.length - 1;
  const picks = useMemo(() => rankPicks(s.history), [s.history]);

  // Friends trickle into the lobby.
  useEffect(() => {
    const timers = FRIENDS.map((f) => setTimeout(() => dispatch({ type: 'seat', id: f.id }), f.joinAt));
    return () => timers.forEach(clearTimeout);
  }, [s.run]);

  // The phone "reads" Instagram for a few seconds, then takes its seat.
  useEffect(() => {
    if (s.phoneStep !== 'analyzing') return;
    const t = setTimeout(() => dispatch({ type: 'youSeated' }), ANALYZE_MS);
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

  // A short drumroll, then the result. Individual votes are never shown.
  useEffect(() => {
    if (s.phase !== 'reveal') return;
    const t = setTimeout(() => dispatch({ type: 'result' }), REVEAL_MS);
    return () => clearTimeout(t);
  }, [s.phase]);

  // No golden buzzer: roll on to the next trailer, or to the final picks
  // once the queue runs out.
  useEffect(() => {
    if (s.phase !== 'result' || unanimous) return;
    const t = setTimeout(
      () => dispatch(hasNext ? { type: 'playTrailer', movieIdx: s.movieIdx + 1, now: Date.now() } : { type: 'showPicks' }),
      MISS_PAUSE_MS,
    );
    return () => clearTimeout(t);
  }, [s.phase, unanimous, hasNext, s.movieIdx]);

  return {
    s,
    dispatch,
    movie,
    unanimous,
    voteCount,
    hasNext,
    picks,
    completion: completionStatus(s),
    everyoneSeated: D.people.every((p) => s.seated.includes(p.id)),
    start: () => dispatch({ type: 'playTrailer', movieIdx: s.movieIdx, now: Date.now() }),
    nextTrailer: () => dispatch({ type: 'playTrailer', movieIdx: s.movieIdx + 1, now: Date.now() }),
    react: (who, emoji) => dispatch({ type: 'react', reaction: makeReaction(who, emoji) }),
    vote: (vote) => dispatch({ type: 'vote', id: 'you', vote }),
  };
}
