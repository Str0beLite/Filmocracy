// Timings and rules of a night. Shared by the screens and the fake backend.

export const TRAILER_MS = 12000; // placeholder trailers; a real one plays to its end
export const TRAILER_GRACE_MS = 5000; // backstop past a real trailer's end, if the TV never says it ended
export const REVEAL_MS = 0;
export const MISS_MS = 2000;
export const VOTE_TIMEOUT_MS = 60000; // a phone that fell asleep can't stall the night
export const CHECKPOINT_EVERY = 5;
export const REACTION_MS = 2600;

export const isCheckpoint = (n: number) => n % CHECKPOINT_EVERY === 0;
