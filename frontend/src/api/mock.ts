// Mock data for the frontend-only pass. Films, ids and tmdb_ids are real rows
// from backend/catalog/movies.json; feeds, scores and outcomes are made up.

import type { Emote, Feeling, MovieDetails, Person, Rec } from './types';

export const ROOM = { code: 'K7Q2', name: 'Friday movie night' };

export const ME_ID = 'you';

export const PEOPLE: Person[] = [
  { id: 'maya', name: 'Maya', color: '#ff8a5b', feeling: 'laugh' },
  { id: 'jordan', name: 'Jordan', color: '#6fa8ff', feeling: 'hyped' },
  { id: 'sam', name: 'Sam', color: '#c39bff', feeling: 'mindblown' },
  { id: ME_ID, name: 'Alex', color: '#41d6a0', feeling: null },
];

// Boost tags are checked against the catalog's 1,116 tags.
export const FEELINGS: Feeling[] = [
  { id: 'laugh', label: 'Laugh until it hurts', short: 'Laugh', boost: ['comedy', 'funny', 'hilarious'] },
  { id: 'edge', label: 'Be on the edge of my seat', short: 'On edge', boost: ['suspense', 'tense', 'thriller'] },
  { id: 'feels', label: 'Feel all the feels', short: 'Feels', boost: ['emotional', 'touching', 'sad'] },
  { id: 'mindblown', label: 'Have my mind blown', short: 'Mind-blown', boost: ['mindfuck', 'twist ending', 'cerebral'] },
  { id: 'cozy', label: 'Something cozy', short: 'Cozy', boost: ['feel-good', 'heartwarming'] },
  { id: 'hyped', label: 'Get hyped', short: 'Hyped', boost: ['action', 'action packed', 'intense'] },
];

export const EMOTES: Emote[] = [
  { emoji: '🔥', label: 'Fire' },
  { emoji: '😂', label: 'LOL' },
  { emoji: '😱', label: 'Yikes' },
  { emoji: '😍', label: 'Love' },
  { emoji: '🤯', label: 'Mind blown' },
  { emoji: '🥱', label: 'Snooze' },
];

// What "reading" your 3 Explore screenshots finds (POST /feeds returns tags).
export const MY_FEED_TAGS = ['dark humor', 'street food', 'film theory', 'plot twists', 'late-night drives', 'stand-up clips'];

const rec = (r: Omit<Rec, 'rec_id' | 'because_of'> & { because_of?: string[] }): Rec => ({
  rec_id: null,
  because_of: [],
  ...r,
});

// Trailer queue, in the order the night plays them.
export const TRAILERS: Rec[] = [
  rec({ id: 51255, title: 'Hot Fuzz', year: 2007, tmdb_id: 4638, tags: ['british comedy', 'action', 'spoof'], score: 0.24 }),
  rec({ id: 195159, title: 'Spider-Man: Into the Spider-Verse', year: 2018, tmdb_id: 324857, tags: ['visually stunning', 'superheroes', 'original'], score: 0.29 }),
  rec({ id: 168250, title: 'Get Out', year: 2017, tmdb_id: 419430, tags: ['tense', 'suspense', 'social commentary'], score: 0.22 }),
  rec({ id: 152970, title: 'Hunt for the Wilderpeople', year: 2016, tmdb_id: 371645, tags: ['bittersweet', 'touching', 'coming of age'], score: 0.13, explore: true }),
  rec({ id: 111759, title: 'Edge of Tomorrow', year: 2014, tmdb_id: 137113, tags: ['time loop', 'sci-fi', 'action'], score: 0.21 }),
  rec({ id: 122882, title: 'Mad Max: Fury Road', year: 2015, tmdb_id: 76341, tags: ['action', 'post-apocalyptic', 'visually appealing'], score: 0.26 }),
  rec({ id: 4973, title: 'Amélie', year: 2001, tmdb_id: 194, tags: ['feel-good', 'imagination', 'quirky'], score: 0.15, explore: true }),
  rec({ id: 112552, title: 'Whiplash', year: 2014, tmdb_id: 244786, tags: ['intense', 'musicians', 'mentor'], score: 0.2 }),
];

// Scripted result of each trailer (the real one comes from everyone's votes).
// Round 2 is a golden buzzer; 1 and 3–5 miss, so trailer 5 hits the checkpoint.
export const OUTCOMES: ('buzzer' | 'miss')[] = ['miss', 'buzzer', 'miss', 'miss', 'miss', 'buzzer', 'miss', 'miss'];

// The 5 extra recs at the end, from the group's average taste.
export const PREDICTED: Rec[] = [
  rec({ id: 164179, title: 'Arrival', year: 2016, tmdb_id: 329865, tags: ['cerebral', 'aliens'], score: 0.23 }),
  rec({ id: 4963, title: "Ocean's Eleven", year: 2001, tmdb_id: 161, tags: ['heist', 'caper'], score: 0.21 }),
  rec({ id: 109374, title: 'The Grand Budapest Hotel', year: 2014, tmdb_id: 120467, tags: ['stylized', 'quirky'], score: 0.2 }),
  rec({ id: 8874, title: 'Shaun of the Dead', year: 2004, tmdb_id: 747, tags: ['british comedy', 'zombies'], score: 0.19 }),
  rec({ id: 177615, title: 'Lady Bird', year: 2017, tmdb_id: 391713, tags: ['coming of age', 'honest'], score: 0.12, explore: true }),
  rec({ id: 1197, title: 'The Princess Bride', year: 1987, tmdb_id: 2493, tags: ['quotable', 'fairy tale'], score: 0.18 }),
];

// Stand-ins for what TMDB will return, plus placeholder art.
export const DETAILS: Record<number, MovieDetails & { why: { who: string; tag: string }[] }> = {
  51255: {
    runtime: '2h 1m',
    genres: ['Action', 'Comedy'],
    logline: 'A top London cop is reassigned to a sleepy village where the accidents are a little too frequent.',
    palette: ['#1a1410', '#b8432a', '#f3c770'],
    motif: 'rays',
    why: [{ who: 'maya', tag: 'stand-up clips' }, { who: ME_ID, tag: 'dark humor' }],
  },
  195159: {
    runtime: '1h 57m',
    genres: ['Animation', 'Action'],
    logline: 'Brooklyn teen Miles Morales becomes Spider-Man and meets Spider-People from five other dimensions.',
    palette: ['#0b1026', '#ff2e4d', '#28c7fa'],
    motif: 'halftone',
    why: [{ who: 'jordan', tag: 'animation artists' }, { who: 'maya', tag: 'sneaker drops' }],
  },
  168250: {
    runtime: '1h 44m',
    genres: ['Horror', 'Thriller'],
    logline: "A weekend at his girlfriend's family estate turns into something much stranger than awkward.",
    palette: ['#0c0d10', '#5e2b32', '#e6d3b0'],
    motif: 'eye',
    why: [{ who: 'sam', tag: 'social commentary' }, { who: ME_ID, tag: 'plot twists' }],
  },
  152970: {
    runtime: '1h 41m',
    genres: ['Adventure', 'Comedy'],
    logline: 'A defiant city kid and his grumpy foster uncle go on the run in the New Zealand bush.',
    palette: ['#132018', '#c9772f', '#f0dca8'],
    motif: 'horizon',
    why: [{ who: 'maya', tag: 'deadpan comedy' }, { who: 'sam', tag: 'hiking trails' }],
  },
  111759: {
    runtime: '1h 53m',
    genres: ['Sci-fi', 'Action'],
    logline: 'A soldier caught in a time loop relives the same alien battle until he gets it right.',
    palette: ['#10161c', '#6e8796', '#f2b04d'],
    motif: 'rays',
    why: [{ who: 'jordan', tag: 'gaming streams' }, { who: 'sam', tag: 'time travel' }],
  },
  122882: {
    runtime: '2h',
    genres: ['Action', 'Adventure'],
    logline: 'In a desert wasteland, a rebel warrior and a drifter flee a warlord in a two-hour chase.',
    palette: ['#2a1206', '#e0662a', '#f6c48a'],
    motif: 'horizon',
    why: [{ who: 'jordan', tag: 'car builds' }, { who: ME_ID, tag: 'late-night drives' }],
  },
  4973: {
    runtime: '2h 2m',
    genres: ['Romance', 'Comedy'],
    logline: 'A shy Paris waitress decides to secretly change the lives of the people around her.',
    palette: ['#1d0f0c', '#c4352f', '#5f9a5b'],
    motif: 'eye',
    why: [{ who: 'maya', tag: 'cafe vlogs' }, { who: 'sam', tag: 'film photography' }],
  },
  112552: {
    runtime: '1h 47m',
    genres: ['Drama', 'Music'],
    logline: 'A young drummer at an elite conservatory meets a teacher who will stop at nothing.',
    palette: ['#120c06', '#b07a2a', '#f4e1b0'],
    motif: 'rays',
    why: [{ who: 'jordan', tag: 'drum covers' }, { who: ME_ID, tag: 'film theory' }],
  },
  164179: {
    runtime: '1h 56m',
    genres: ['Sci-fi', 'Drama'],
    logline: 'A linguist races to understand alien visitors before the world panics.',
    palette: ['#0e1418', '#5d7480', '#d9dfe0'],
    motif: 'eye',
    why: [{ who: 'sam', tag: 'space facts' }],
  },
  4963: {
    runtime: '1h 56m',
    genres: ['Heist', 'Comedy'],
    logline: 'Eleven specialists plan to rob three Las Vegas casinos in one night.',
    palette: ['#0d1a2b', '#c99a3b', '#f4e3b5'],
    motif: 'halftone',
    why: [{ who: 'jordan', tag: 'suits' }],
  },
  109374: {
    runtime: '1h 40m',
    genres: ['Comedy', 'Adventure'],
    logline: 'A legendary concierge and his lobby boy get tangled up in a stolen painting.',
    palette: ['#3a1428', '#e8879e', '#f6d3c4'],
    motif: 'rays',
    why: [{ who: 'maya', tag: 'pastel interiors' }],
  },
  8874: {
    runtime: '1h 39m',
    genres: ['Comedy', 'Horror'],
    logline: 'A London slacker tries to sort out his life during a zombie outbreak.',
    palette: ['#1a1212', '#9b2a24', '#e9d9b0'],
    motif: 'halftone',
    why: [{ who: ME_ID, tag: 'dark humor' }],
  },
  177615: {
    runtime: '1h 34m',
    genres: ['Comedy', 'Drama'],
    logline: 'A Sacramento high-school senior spends her last year at home fighting with her mother.',
    palette: ['#1e1416', '#d47a6a', '#f2d7c4'],
    motif: 'horizon',
    why: [{ who: 'sam', tag: 'indie playlists' }],
  },
  1197: {
    runtime: '1h 38m',
    genres: ['Adventure', 'Fantasy'],
    logline: 'A farmhand turned pirate fights giants, swordsmen and a prince to rescue his true love.',
    palette: ['#14112a', '#7a5cc4', '#f1d48a'],
    motif: 'eye',
    why: [{ who: 'maya', tag: 'fairy tale edits' }],
  },
};
