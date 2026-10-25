// One URL per screen. The TV and phone frames navigate between them as the
// room changes, so the URL always says which screen a device is on.

import { createBrowserRouter, redirect } from 'react-router';
import { DevIndex } from './dev/DevIndex';
import { TVFrame } from './tv/TVFrame';
import * as TV from './tv/screens';
import { PhoneSettings } from './phone/Settings';
import { PhoneFrame } from './phone/PhoneFrame';
import * as Phone from './phone/screens';
import { Training } from './training/Training';

export const router = createBrowserRouter([
  { path: '/training', element: <Training /> },
  import.meta.env.DEV ? { path: '/', element: <DevIndex /> } : { path: '/', loader: () => redirect('/tv') },
  {
    path: '/tv',
    element: <TVFrame />,
    children: [
      { index: true, element: null },
      { path: 'lobby', element: <TV.TVLobby /> },
      { path: 'trailer/:n', element: <TV.TVTrailer /> },
      { path: 'vote/:n', element: <TV.TVVote /> },
      { path: 'reveal/:n', element: <TV.TVReveal /> },
      { path: 'miss/:n', element: <TV.TVMiss /> },
      { path: 'checkpoint/:n', element: <TV.TVCheckpoint /> },
      { path: 'buzzer/:n', element: <TV.TVBuzzer /> },
      { path: 'picks', element: <TV.TVPicks /> },
      { path: 'showing/:id?', element: <TV.TVShowing /> },
    ],
  },
  {
    path: '/phone',
    element: <PhoneFrame />,
    children: [
      { index: true, element: null },
      { path: 'settings', element: <PhoneSettings /> },
      { path: 'join', element: <Phone.PhoneJoin /> },
      { path: 'sign-in', loader: () => redirect('/phone/name') },
      { path: 'name', element: <Phone.PhoneName /> },
      { path: 'feeling', element: <Phone.PhoneFeeling /> },
      { path: 'screenshots', element: <Phone.PhoneScreenshots /> },
      { path: 'reading', element: <Phone.PhoneReading /> },
      { path: 'lobby', element: <Phone.PhoneLobby /> },
      { path: 'react/:n', element: <Phone.PhoneReact /> },
      { path: 'vote/:n', element: <Phone.PhoneVote /> },
      { path: 'voted/:n', element: <Phone.PhoneVoted /> },
      { path: 'miss/:n', element: <Phone.PhoneMiss /> },
      { path: 'checkpoint/:n', element: <Phone.PhoneCheckpoint /> },
      { path: 'buzzer/:n', element: <Phone.PhoneBuzzer /> },
      { path: 'picks', element: <Phone.PhonePicks /> },
      { path: 'showing/:id?', element: <Phone.PhoneShowing /> },
    ],
  },
  { path: '*', loader: () => redirect('/') },
]);
