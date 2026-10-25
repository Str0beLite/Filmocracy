// Fixed lists the screens share: seat colours, tonight's feelings, reactions,
// and generated art for films without a poster.

import type { Emote, Feeling, MovieDetails } from './types';

// Seat colours, handed out in join order.
export const COLORS = ['#ff8a5b', '#6fa8ff', '#c39bff', '#41d6a0', '#ffd166', '#ff7eb6', '#7ee0e0', '#f4a261'];

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

// Placeholder art, picked from the film's id so it's stable across screens.
const PALETTES: MovieDetails['palette'][] = [
  ['#1a1410', '#b8432a', '#f3c770'],
  ['#0b1026', '#ff2e4d', '#28c7fa'],
  ['#0c0d10', '#5e2b32', '#e6d3b0'],
  ['#132018', '#c9772f', '#f0dca8'],
  ['#10161c', '#6e8796', '#f2b04d'],
  ['#2a1206', '#e0662a', '#f6c48a'],
  ['#1d0f0c', '#c4352f', '#5f9a5b'],
  ['#120c06', '#b07a2a', '#f4e1b0'],
];
const MOTIFS: MovieDetails['motif'][] = ['rays', 'eye', 'halftone', 'horizon'];

export const art = (id: number) => ({ palette: PALETTES[id % PALETTES.length], motif: MOTIFS[id % MOTIFS.length] });
