// Demo content. Everything the prototype shows lives here, so you can swap
// movies, friends and copy without touching the screens.
window.TANDEM = {
  room: { code: 'K7Q2', name: 'Friday movie night' },

  // What each person can say they want to feel tonight.
  moods: [
    { id: 'laugh', emoji: '😂', label: 'Laugh until it hurts', short: 'Laugh' },
    { id: 'thrill', emoji: '😱', label: 'Be on the edge of my seat', short: 'On edge' },
    { id: 'cry', emoji: '🥹', label: 'Feel all the feels', short: 'Feels' },
    { id: 'mindblown', emoji: '🤯', label: 'Have my mind blown', short: 'Mind-blown' },
    { id: 'cozy', emoji: '🥰', label: 'Something cozy', short: 'Cozy' },
    { id: 'hyped', emoji: '🔥', label: 'Get hyped', short: 'Hyped' },
  ],

  // The friend group, in seat order. `joinAt` is when (ms after the demo
  // starts) each friend scans in. "you" is whoever holds the demo phone and
  // picks a mood on it.
  people: [
    { id: 'maya', name: 'Maya', color: '#ff8a5b', mood: 'laugh', joinAt: 1600 },
    { id: 'jordan', name: 'Jordan', color: '#6fa8ff', mood: 'hyped', joinAt: 3400 },
    { id: 'sam', name: 'Sam', color: '#c39bff', mood: 'mindblown', joinAt: 5200 },
    { id: 'you', name: 'You', color: '#41d6a0' },
  ],

  // What the phone "finds" while it reads your Instagram.
  you: {
    signals: [
      'Read 1,204 reels you liked',
      'Found 38 saved whodunit edits',
      'You finish film-theory videos',
      'Lots of dark comedy in your feed',
    ],
  },

  emotes: [
    { emoji: '🔥', label: 'Fire' },
    { emoji: '😂', label: 'LOL' },
    { emoji: '😱', label: 'Yikes' },
    { emoji: '😍', label: 'Love' },
    { emoji: '🤯', label: 'Mind blown' },
    { emoji: '🥱', label: 'Snooze' },
  ],

  // Trailer queue. `match` is the model's predicted chance everyone says yes.
  // `votes` scripts how the friends vote: the first trailer misses (Sam
  // passes) and the second hits the golden buzzer if you say yes.
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
      moods: ['mindblown', 'laugh'],
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
      moods: ['laugh', 'mindblown', 'hyped', 'cry'],
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
      moods: ['hyped', 'mindblown'],
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
      moods: ['cry', 'cozy'],
      why: [
        { who: 'sam', text: 'saves rainy-day film stills' },
        { who: 'you', text: 'lingers on travel reels' },
      ],
      vibes: ['😍', '🥱', '😍'],
      votes: { maya: 'yes', jordan: 'no', sam: 'yes' },
    },
  ],

  // The 5 extra recommendations shown at the end, ranked by predicted match.
  predicted: [
    { id: 'parasite', title: 'Parasite', year: 2019, genres: ['Thriller', 'Dark comedy'], match: 87, palette: ['#14201a', '#6f8f5a', '#e9e2c8'], motif: 'horizon' },
    { id: 'paddington-2', title: 'Paddington 2', year: 2017, genres: ['Comedy', 'Family'], match: 84, palette: ['#2a1410', '#c8452c', '#f2c14e'], motif: 'rays' },
    { id: 'arrival', title: 'Arrival', year: 2016, genres: ['Sci-fi', 'Drama'], match: 81, palette: ['#0e1418', '#5d7480', '#d9dfe0'], motif: 'eye' },
    { id: 'oceans-eleven', title: "Ocean's Eleven", year: 2001, genres: ['Heist', 'Comedy'], match: 79, palette: ['#0d1a2b', '#c99a3b', '#f4e3b5'], motif: 'halftone' },
    { id: 'grand-budapest', title: 'The Grand Budapest Hotel', year: 2014, genres: ['Comedy', 'Adventure'], match: 76, palette: ['#3a1428', '#e8879e', '#f6d3c4'], motif: 'rays' },
  ],
};
