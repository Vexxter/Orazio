// When the live quote stream counts as healthy, and when the page should fall back to polling.
// Pure, so it is unit-tested in Node (tests/frontend/stream-policy.test.mjs).
//
// The server sends a `quote` event on every change and a `ping` event every ~15 s while nothing
// changes (a closed market is silent), so "no event for 20 s" means the connection is dead, not idle.

export const MAX_SILENCE_MS = 20000;

export function isStreamHealthy({ lastEventAt, now, maxSilenceMs = MAX_SILENCE_MS }) {
  return lastEventAt !== null && lastEventAt !== undefined && now - lastEventAt <= maxSilenceMs;
}

// Poll only when the stream is not delivering AND no poll is already in flight.
export function shouldPoll({ streamHealthy, quotesInFlight }) {
  return !streamHealthy && quotesInFlight === 0;
}
