// One URL per screen. Loaders fetch through src/api, so wiring the backend
// changes api/index.ts and nothing here.

import { createBrowserRouter, redirect, type LoaderFunctionArgs } from 'react-router';
import { getMyFeedTags, getPicks, getRoom, getRound, getRounds } from './api';
import { DevIndex } from './dev/DevIndex';
import { TVFrame } from './tv/TVFrame';
import * as TV from './tv/screens';
import { PhoneFrame } from './phone/PhoneFrame';
import * as Phone from './phone/screens';

const roundOf = ({ params }: LoaderFunctionArgs) => Math.max(1, Number(params.n) || 1);

const roundData = async (args: LoaderFunctionArgs) => ({ room: await getRoom(), round: await getRound(roundOf(args)) });
const picksData = async () => ({ picks: await getPicks() });

// The movie that's playing: the one picked, or tonight's #1.
const showingData = async ({ params }: LoaderFunctionArgs) => {
  const { top, more } = await getPicks();
  const all = [...top.map((p) => p.movie), ...more];
  return { title: (all.find((m) => m.id === Number(params.id)) ?? top[0].movie).title };
};

export const router = createBrowserRouter([
  import.meta.env.DEV ? { path: '/', element: <DevIndex /> } : { path: '/', loader: () => redirect('/tv/lobby') },
  {
    path: '/tv',
    element: <TVFrame />,
    children: [
      { index: true, loader: () => redirect('/tv/lobby') },
      { path: 'lobby', loader: getRoom, element: <TV.TVLobby /> },
      { path: 'trailer/:n', loader: roundData, element: <TV.TVTrailer /> },
      { path: 'vote/:n', loader: roundData, element: <TV.TVVote /> },
      { path: 'reveal/:n', loader: roundData, element: <TV.TVReveal /> },
      { path: 'miss/:n', loader: roundData, element: <TV.TVMiss /> },
      {
        path: 'checkpoint/:n',
        loader: async (args) => ({ ...(await roundData(args)), watched: await getRounds(1, roundOf(args)) }),
        element: <TV.TVCheckpoint />,
      },
      { path: 'buzzer/:n', loader: roundData, element: <TV.TVBuzzer /> },
      { path: 'picks', loader: picksData, element: <TV.TVPicks /> },
      { path: 'showing/:id?', loader: showingData, element: <TV.TVShowing /> },
    ],
  },
  {
    path: '/phone',
    element: <PhoneFrame />,
    children: [
      { index: true, loader: () => redirect('/phone/join') },
      { path: 'join', loader: getRoom, element: <Phone.PhoneJoin /> },
      { path: 'sign-in', loader: getRoom, element: <Phone.PhoneSignIn /> },
      { path: 'feeling', loader: getRoom, element: <Phone.PhoneFeeling /> },
      { path: 'screenshots', loader: getRoom, element: <Phone.PhoneScreenshots /> },
      { path: 'reading', loader: getMyFeedTags, element: <Phone.PhoneReading /> },
      { path: 'lobby', loader: getRoom, element: <Phone.PhoneLobby /> },
      { path: 'react/:n', loader: roundData, element: <Phone.PhoneReact /> },
      { path: 'vote/:n', loader: roundData, element: <Phone.PhoneVote /> },
      { path: 'voted/:n', loader: roundData, element: <Phone.PhoneVoted /> },
      { path: 'miss/:n', loader: roundData, element: <Phone.PhoneMiss /> },
      { path: 'checkpoint/:n', loader: roundData, element: <Phone.PhoneCheckpoint /> },
      { path: 'buzzer/:n', loader: roundData, element: <Phone.PhoneBuzzer /> },
      { path: 'picks', loader: picksData, element: <Phone.PhonePicks /> },
      { path: 'showing/:id?', loader: showingData, element: <Phone.PhoneShowing /> },
    ],
  },
  { path: '*', loader: () => redirect('/') },
]);
