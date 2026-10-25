// Demo content. Everything the prototype shows lives here, so you can swap
// movies, friends and copy without touching the screens.
window.TANDEM = {
  room: { code: 'K7Q2', name: 'Friday movie night' },

  // The friend group, in seat order. `joinAt` is when (ms after the demo
  // starts) each friend scans in. "you" is whoever holds the demo phone.
  people: [
    { id: 'maya', name: 'Maya', color: '#ff8a5b', vibe: 'Chaos Comedian', joinAt: 1600 },
    { id: 'jordan', name: 'Jordan', color: '#6fa8ff', vibe: 'Popcorn Purist', joinAt: 3400 },
    { id: 'sam', name: 'Sam', color: '#c39bff', vibe: 'Soft-Hearted Cynic', joinAt: 5200 },
    { id: 'you', name: 'You', color: '#41d6a0', vibe: 'Plot-Twist Chaser' },
  ],

  // What the phone "finds" while it reads your Instagram.
  you: {
    signals: [
      'Read 1,204 reels you liked',
      'Found 38 saved whodunit edits',
      'You finish film-theory videos',
      'Lots of dark comedy in your feed',
    ],
    vibe: {
      title: 'The Plot-Twist Chaser',
      blurb: 'You save reveal edits and argue theories in the comments. Bring on the rug-pulls.',
      traits: [['Twists', 92], ['Laughs', 71], ['Spectacle', 54], ['Feels', 38]],
      tags: ['Whodunits', 'Dark comedy', 'Mind-benders'],
    },
  },

  emotes: [
    { emoji: '🔥', label: 'Fire' },
    { emoji: '😂', label: 'LOL' },
    { emoji: '😱', label: 'Yikes' },
    { emoji: '😍', label: 'Love' },
    { emoji: '🤯', label: 'Mind blown' },
    { emoji: '🥱', label: 'Snooze' },
  ],

  // Trailer queue. `votes` scripts how the friends vote: the first trailer
  // misses (Sam passes) and the second hits the golden buzzer if you say yes.
  // `palette` + `motif` drive the placeholder poster and trailer art.
  movies: [
    {
      id: 'knives-out',
      title: 'Knives Out',
      year: 2019,
      runtime: '2h 10m',
      genres: ['Mystery', 'Comedy'],
      logline: 'A crime novelist is found dead after his 85th birthday party, and every heir in the house has a motive.',
      match: 88,
      palette: ['#24170f', '#9a6a33', '#e8c88f'],
      motif: 'rays',
      why: [
        { who: 'maya', text: 'saves whodunit edits' },
        { who: 'you', text: 'liked 9 plot-twist reels' },
      ],
      vibes: ['🤯', '😂', '😱', '🔥'],
      votes: { maya: 'yes', jordan: 'yes', sam: 'no' },
    },
    {
      id: 'eeaao',
      title: 'Everything Everywhere All at Once',
      year: 2022,
      runtime: '2h 19m',
      genres: ['Sci-fi', 'Comedy', 'Action'],
      logline: 'A laundromat owner in the middle of a tax audit gets pulled across the multiverse to save it, and her family.',
      match: 96,
      palette: ['#1b0f3a', '#ff4fa3', '#ffd166'],
      motif: 'eye',
      why: [
        { who: 'jordan', text: 'replays kung-fu fight reels' },
        { who: 'sam', text: 'shares absurdist memes' },
      ],
      vibes: ['🤯', '😂', '😍', '🔥'],
      votes: { maya: 'yes', jordan: 'yes', sam: 'yes' },
    },
    {
      id: 'spider-verse',
      title: 'Spider-Man: Across the Spider-Verse',
      year: 2023,
      runtime: '2h 20m',
      genres: ['Animation', 'Action'],
      logline: 'Miles Morales swings into a multiverse full of Spider-People who disagree about how his story should go.',
      match: 91,
      palette: ['#0b1026', '#ff2e4d', '#28c7fa'],
      motif: 'halftone',
      why: [
        { who: 'jordan', text: 'follows 4 animation artists' },
        { who: 'maya', text: 'watches every sneaker drop' },
      ],
      vibes: ['🔥', '😍', '🤯'],
      votes: { maya: 'yes', jordan: 'yes', sam: 'yes' },
    },
    {
      id: 'past-lives',
      title: 'Past Lives',
      year: 2023,
      runtime: '1h 46m',
      genres: ['Romance', 'Drama'],
      logline: 'Childhood friends separated when one family leaves Seoul meet again in New York, two decades later.',
      match: 79,
      palette: ['#0f2233', '#e98a6b', '#f6d6b8'],
      motif: 'horizon',
      why: [
        { who: 'sam', text: 'saves rainy-day film stills' },
        { who: 'you', text: 'lingers on travel reels' },
      ],
      vibes: ['😍', '🥱', '😍'],
      votes: { maya: 'yes', jordan: 'no', sam: 'yes' },
    },
  ],
};
